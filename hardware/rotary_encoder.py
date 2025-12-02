"""Rotary encoder handling for volume control."""
import logging
import re
import subprocess
import threading
from datetime import datetime, time
from typing import Optional, Callable
from gpiozero import DigitalInputDevice
from signal import pause

logger = logging.getLogger(__name__)


class VolumeController:
    """Controls system audio volume using amixer."""
    
    def __init__(self, mixer_control: str = 'PCM', card: int = 0, max_db: float = -1.0,
                 time_limit_day_db: float = 0.0, time_limit_evening_db: float = -5.0, 
                 time_limit_night_db: float = -10.0):
        """
        Initialize volume controller.
        
        Args:
            mixer_control: ALSA mixer control name (default: 'PCM')
            card: ALSA card number (default: 0)
            max_db: Maximum volume in dB (default: -1.0 to prevent clipping)
            time_limit_day_db: dB offset for day hours 9am-5pm (default: 0.0)
            time_limit_evening_db: dB offset for evening transition 6pm-7pm and 8am-9am (default: -7.0)
            time_limit_night_db: dB offset for night hours 7pm-7am (default: -14.0)
        """
        self.mixer_control = mixer_control
        self.card = card
        self._base_max_db = max_db  # Base maximum dB limit (original limit, not time-limited)
        self.max_db = max_db  # Current effective maximum dB limit (may be time-limited)
        self._volume_lock = threading.Lock()
        self._min_db = None
        self._max_db_raw = None
        self._numid = None  # Cache numid after first lookup
        self._current_volume = self.get_volume()
        self._get_mixer_limits()
        
        # Time-based limiting configuration
        self._time_limit_day_db = time_limit_day_db
        self._time_limit_evening_db = time_limit_evening_db
        self._time_limit_night_db = time_limit_night_db
        
        # Time-based limiting thread
        self._time_limit_thread = None
        self._time_limit_stop = threading.Event()
        
        # Initialize time-based limit
        self._update_time_based_limit()
        
        # Start background thread for time-based limiting
        self._start_time_limit_thread()
        
        logger.info(f"Volume controller initialized (control: {mixer_control}, card: {card}, base max: {max_db}dB, "
                   f"time limits: day={time_limit_day_db}dB, evening={time_limit_evening_db}dB, night={time_limit_night_db}dB)")
    
    def _get_control_numid(self) -> Optional[int]:
        """Get the numid for the mixer control (cached after first lookup)."""
        if self._numid is not None:
            return self._numid
        
        try:
            result = subprocess.run(
                ['amixer', '-c', str(self.card), 'sget', self.mixer_control],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            # Parse numid from output - format: "numid=1,iface=MIXER,name='PCM Playback Volume'"
            for line in result.stdout.split('\n'):
                if 'numid=' in line:
                    match = re.search(r'numid=(\d+)', line)
                    if match:
                        numid = int(match.group(1))
                        # Cache it
                        self._numid = numid
                        logger.debug(f"Found numid={numid} for {self.mixer_control}")
                        return numid
            
            # Fallback: For PCM on most systems, numid is 1
            # Try it and cache if it works
            logger.debug("Could not parse numid from sget, trying numid=1 as fallback")
            test_result = subprocess.run(
                ['amixer', '-c', str(self.card), 'cset', 'numid=1', '--', '0'],
                capture_output=True,
                text=True,
                timeout=1
            )
            if test_result.returncode == 0:
                self._numid = 1
                return 1
            
            return None
        except Exception as e:
            logger.debug(f"Error getting numid: {e}")
            return None
    
    def _get_mixer_limits(self):
        """Get mixer limits and calculate effective range."""
        try:
            result = subprocess.run(
                ['amixer', '-c', str(self.card), 'sget', self.mixer_control],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            # Parse limits like: "Limits: Playback -10239 - 400"
            for line in result.stdout.split('\n'):
                if 'Limits:' in line:
                    # Extract min and max (in hundredths of dB)
                    # Format: "Limits: Playback -10239 - 400"
                    match = re.search(r'Limits:\s*Playback\s+(-?\d+)\s+-\s+(-?\d+)', line)
                    if match:
                        try:
                            min_db_raw = int(match.group(1))  # e.g., -10239
                            max_db_raw = int(match.group(2))  # e.g., 400
                            self._min_db = min_db_raw / 100.0  # Convert to dB
                            self._max_db_raw = max_db_raw
                            logger.debug(f"Mixer limits: {self._min_db}dB to {max_db_raw/100.0}dB")
                            return
                        except (ValueError, IndexError) as e:
                            logger.debug(f"Error parsing limits: {e}")
                            pass
            
            logger.warning("Could not parse mixer limits, using defaults")
            self._min_db = -102.39
            self._max_db_raw = 400
        except Exception as e:
            logger.warning(f"Error getting mixer limits: {e}, using defaults")
            self._min_db = -102.39
            self._max_db_raw = 400
    
    def _get_time_based_db_offset(self) -> float:
        """
        Get the current time-based dB offset.
        
        Schedule:
        - 5pm-6pm: day_db (default: 0dB)
        - 6pm-7pm: evening_db (default: -7dB)
        - 7pm-7am: night_db (default: -14dB)
        - 7am-8am: night_db (default: -14dB)
        - 8am-9am: evening_db (default: -7dB)
        - 9am-5pm: day_db (default: 0dB)
        
        Returns:
            dB offset based on configured values
        """
        now = datetime.now().time()
        
        # Night period: 7pm (19:00) to 7am (07:00)
        if time(19, 0) <= now or now < time(7, 0):
            return self._time_limit_night_db
        
        # Morning transition: 7am-8am stays at night_db
        if time(7, 0) <= now < time(8, 0):
            return self._time_limit_night_db
        
        # Morning transition: 8am-9am increases to evening_db
        if time(8, 0) <= now < time(9, 0):
            return self._time_limit_evening_db
        
        # Day period: 9am-5pm at day_db
        if time(9, 0) <= now < time(17, 0):
            return self._time_limit_day_db
        
        # Evening transition: 5pm-6pm stays at day_db
        if time(17, 0) <= now < time(18, 0):
            return self._time_limit_day_db
        
        # Evening transition: 6pm-7pm decreases to evening_db
        if time(18, 0) <= now < time(19, 0):
            return self._time_limit_evening_db
        
        # Default fallback (shouldn't reach here)
        return self._time_limit_day_db
    
    def _update_time_based_limit(self):
        """Update the effective max_db based on current time and reduce volume if needed."""
        # Calculate new time-based max_db
        db_offset = self._get_time_based_db_offset()
        new_max_db = self._base_max_db + db_offset
        old_max_db = self.max_db
        
        with self._volume_lock:
            # Update the effective max_db
            self.max_db = new_max_db
            
            # Get current volume dB value from amixer
            try:
                result = subprocess.run(
                    ['amixer', 'get', self.mixer_control, f'{self.card}'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                
                current_db_value = None
                for line in result.stdout.split('\n'):
                    if 'Playback' in line and 'dB' in line:
                        db_match = re.search(r'\[(-?\d+\.?\d*)dB\]', line)
                        if db_match:
                            try:
                                current_db_value = float(db_match.group(1))
                                break
                            except ValueError:
                                pass
                
                if current_db_value is not None:
                    # Check if current volume exceeds the new limit
                    if current_db_value > new_max_db:
                        # Current volume exceeds new limit, reduce it
                        logger.info(f"Time-based limit changed: reducing volume from {current_db_value:.2f}dB to {new_max_db:.2f}dB (offset: {db_offset}dB)")
                        # Set volume to the new maximum
                        db_raw = int(new_max_db * 100)
                        numid = self._get_control_numid()
                        if numid:
                            result = subprocess.run(
                                ['amixer', '-q', '-c', str(self.card), 'cset', f'numid={numid}', '--', str(db_raw)],
                                capture_output=True,
                                text=True,
                                timeout=2
                            )
                            if result.returncode == 0:
                                # Update current volume percentage
                                self._current_volume = self._db_to_percentage(new_max_db)
                                logger.info(f"Volume reduced to {new_max_db:.2f}dB ({self._current_volume}%)")
                        else:
                            # Fallback: use percentage
                            max_percent = self._db_to_percentage(new_max_db)
                            result = subprocess.run(
                                ['amixer', '-q', '-c', str(self.card), 'set', self.mixer_control, f'{max_percent}%'],
                                capture_output=True,
                                text=True,
                                timeout=2
                            )
                            if result.returncode == 0:
                                self._current_volume = max_percent
                                logger.info(f"Volume reduced to {new_max_db:.2f}dB ({max_percent}%)")
                    else:
                        logger.debug(f"Time-based limit updated: max_db={new_max_db:.2f}dB (offset: {db_offset}dB), current volume={current_db_value:.2f}dB")
                else:
                    logger.debug(f"Time-based limit updated: max_db={new_max_db:.2f}dB (offset: {db_offset}dB)")
            except Exception as e:
                logger.debug(f"Error checking current volume for time-based limit: {e}")
                logger.debug(f"Time-based limit updated: max_db={new_max_db:.2f}dB (offset: {db_offset}dB)")
    
    def _start_time_limit_thread(self):
        """Start background thread that periodically updates time-based volume limits."""
        def time_limit_worker():
            """Worker thread that checks time every 5 minutes."""
            while not self._time_limit_stop.wait(300):  # Wait 5 minutes (300 seconds)
                try:
                    self._update_time_based_limit()
                except Exception as e:
                    logger.error(f"Error updating time-based limit: {e}")
        
        self._time_limit_thread = threading.Thread(target=time_limit_worker, daemon=True)
        self._time_limit_thread.start()
        logger.info("Time-based volume limiting thread started")
    
    def _db_to_percentage(self, db_value: float) -> int:
        """
        Convert dB value to percentage based on effective range.
        
        Args:
            db_value: Volume in dB
            
        Returns:
            Percentage (0-100)
        """
        if self._min_db is None:
            self._get_mixer_limits()
        
        # Effective range: min_db to max_db (limited)
        effective_min = self._min_db
        effective_max = self.max_db
        
        # Clamp to effective range
        db_value = max(effective_min, min(effective_max, db_value))
        
        # Convert to percentage
        if effective_max == effective_min:
            return 100
        
        percentage = int(((db_value - effective_min) / (effective_max - effective_min)) * 100)
        return max(0, min(100, percentage))
    
    def _percentage_to_db(self, percentage: int) -> float:
        """
        Convert percentage to dB value within effective range.
        
        Args:
            percentage: Volume percentage (0-100)
            
        Returns:
            Volume in dB
        """
        if self._min_db is None:
            self._get_mixer_limits()
        
        # Effective range: min_db to max_db (limited)
        effective_min = self._min_db
        effective_max = self.max_db
        
        # Clamp percentage
        percentage = max(0, min(100, percentage))
        
        # Convert to dB
        if percentage == 0:
            return effective_min  # Mute at minimum
        
        db_value = effective_min + ((percentage / 100.0) * (effective_max - effective_min))
        return db_value
    
    def get_volume(self) -> int:
        """
        Get current volume percentage (0-100) based on effective range.
        
        Returns:
            Current volume as integer (0-100)
        """
        try:
            result = subprocess.run(
                ['amixer', 'get', self.mixer_control, f'{self.card}'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            # Parse output for dB value: "Mono: Playback -26 [96%] [-0.26dB]"
            for line in result.stdout.split('\n'):
                if 'Playback' in line and 'dB' in line:
                    # Try to extract dB value
                    db_match = re.search(r'\[(-?\d+\.?\d*)dB\]', line)
                    if db_match:
                        try:
                            db_value = float(db_match.group(1))
                            volume = self._db_to_percentage(db_value)
                            self._current_volume = volume
                            return volume
                        except ValueError:
                            pass
                    
                    # Fallback: try percentage
                    if '%' in line:
                        parts = line.split('[')
                        if len(parts) > 1:
                            percent_str = parts[1].split('%')[0]
                            try:
                                volume = int(percent_str)
                                # Convert to effective percentage based on dB limit
                                # This is approximate - better to use dB directly
                                self._current_volume = volume
                                return volume
                            except ValueError:
                                pass
            
            logger.warning("Could not parse volume from amixer output")
            return self._current_volume
        except Exception as e:
            logger.error(f"Error getting volume: {e}")
            return self._current_volume
    
    def set_volume(self, volume: int) -> bool:
        """
        Set volume percentage (clamped to max_db limit).
        
        Args:
            volume: Volume percentage (0-100)
            
        Returns:
            True if successful
        """
        volume = max(0, min(100, volume))  # Clamp to 0-100
        
        # Convert percentage to dB within effective range
        db_value = self._percentage_to_db(volume)
        
        # Convert dB to amixer format (hundredths of dB, e.g., -100 for -1.00dB)
        db_raw = int(db_value * 100)
        
        try:
            with self._volume_lock:
                # Set volume using dB value via cset to ensure we respect the limit
                # First get the numid for the control
                numid = self._get_control_numid()
                if numid:
                    # Use cset with numid for precise dB control
                    # Use -q (quiet) flag to reduce output and potential audio glitches
                    result = subprocess.run(
                        ['amixer', '-q', '-c', str(self.card), 'cset', f'numid={numid}', '--', str(db_raw)],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                else:
                    # Fallback: use percentage (less precise but should work)
                    # Calculate what percentage corresponds to max_db
                    max_percent = self._db_to_percentage(self.max_db)
                    if volume > max_percent:
                        volume = max_percent
                    # Use -q (quiet) flag to reduce output and potential audio glitches
                    result = subprocess.run(
                        ['amixer', '-q', '-c', str(self.card), 'set', self.mixer_control, f'{volume}%'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                
                if result.returncode == 0:
                    self._current_volume = volume
                    logger.info(f"Volume set to {volume}% ({db_value:.2f}dB, max: {self.max_db}dB)")
                    return True
                else:
                    logger.error(f"Failed to set volume: {result.stderr}")
                    return False
        except Exception as e:
            logger.error(f"Error setting volume: {e}")
            return False
    
    def adjust_volume(self, delta: int) -> bool:
        """
        Adjust volume by delta.
        
        Args:
            delta: Change in volume (-100 to 100)
            
        Returns:
            True if successful
        """
        current = self.get_volume()
        new_volume = current + delta
        return self.set_volume(new_volume)
    
    def mute(self) -> bool:
        """Mute audio."""
        try:
            result = subprocess.run(
                ['amixer', '-c', str(self.card), 'set', self.mixer_control, 'mute'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                logger.info("Audio muted")
                return True
            return False
        except Exception as e:
            logger.error(f"Error muting: {e}")
            return False
    
    def unmute(self) -> bool:
        """Unmute audio."""
        try:
            result = subprocess.run(
                ['amixer', '-c', str(self.card), 'set', self.mixer_control, 'unmute'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                logger.info("Audio unmuted")
                return True
            return False
        except Exception as e:
            logger.error(f"Error unmuting: {e}")
            return False
    
    def toggle_mute(self) -> bool:
        """Toggle mute state."""
        try:
            result = subprocess.run(
                ['amixer', 'get', self.mixer_control, f'{self.card}'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            # Check if muted
            is_muted = '[off]' in result.stdout or '[Mono]' in result.stdout
            
            if is_muted:
                return self.unmute()
            else:
                return self.mute()
        except Exception as e:
            logger.error(f"Error toggling mute: {e}")
            return False
    
    def close(self):
        """Clean up resources, including time-based limiting thread."""
        # Stop time-based limiting thread
        if self._time_limit_thread and self._time_limit_thread.is_alive():
            self._time_limit_stop.set()
            self._time_limit_thread.join(timeout=2.0)
            logger.info("Time-based volume limiting thread stopped")


class RotaryEncoder:
    """Handles rotary encoder input for volume control."""
    
    def __init__(self, clk_pin: int, dt_pin: int, sw_pin: Optional[int] = None,
                 volume_step: int = 2, volume_controller: Optional[VolumeController] = None,
                 time_limit_day_db: float = 0.0, time_limit_evening_db: float = -7.0,
                 time_limit_night_db: float = -14.0):
        """
        Initialize rotary encoder.
        
        Args:
            clk_pin: GPIO pin for CLK (clock) signal
            dt_pin: GPIO pin for DT (data) signal
            sw_pin: Optional GPIO pin for switch/button (for mute toggle)
            volume_step: Volume change per encoder step (default: 2%)
            volume_controller: VolumeController instance (creates default if None)
            time_limit_day_db: dB offset for day hours 9am-5pm (default: 0.0)
            time_limit_evening_db: dB offset for evening transition 6pm-7pm and 8am-9am (default: -7.0)
            time_limit_night_db: dB offset for night hours 7pm-7am (default: -14.0)
        """
        self.clk_pin = clk_pin
        self.dt_pin = dt_pin
        self.sw_pin = sw_pin
        self.volume_step = volume_step
        
        self.volume_controller = volume_controller or VolumeController(
            time_limit_day_db=time_limit_day_db,
            time_limit_evening_db=time_limit_evening_db,
            time_limit_night_db=time_limit_night_db
        )
        
        # GPIO devices
        self.clk = None
        self.dt = None
        self.sw = None
        
        # State tracking
        self.clk_last_state = None
        self.dt_last_state = None
        self.rotation_lock = threading.Lock()
        
        # Rate limiting for smooth operation
        self._last_rotation_time = 0
        self._min_rotation_interval = 0.02  # Minimum 50ms between volume adjustments (20 adjustments/sec max) - prevents audio noise
        
        # Quadrature state tracking for proper decoding
        self._quadrature_state = 0  # 0-3 representing the 4 states of quadrature
        
        # Callbacks
        self.on_volume_change: Optional[Callable[[int], None]] = None
        self.on_mute_toggle: Optional[Callable[[], None]] = None
        
        self._setup_encoder()
    
    def _setup_encoder(self):
        """Set up GPIO pins for rotary encoder."""
        try:
            # Set up CLK and DT pins as inputs with pull-up
            self.clk = DigitalInputDevice(self.clk_pin, pull_up=True)
            self.dt = DigitalInputDevice(self.dt_pin, pull_up=True)
            
            # Read initial state
            self.clk_last_state = self.clk.value
            self.dt_last_state = self.dt.value
            
            # Set up callbacks for rotation detection on both pins
            self.clk.when_activated = self._on_clk_change
            self.clk.when_deactivated = self._on_clk_change
            self.dt.when_activated = self._on_dt_change
            self.dt.when_deactivated = self._on_dt_change
            
            logger.info(f"Rotary encoder initialized: CLK=GPIO{self.clk_pin}, DT=GPIO{self.dt_pin}")
            
            # Set up switch/button if provided
            if self.sw_pin is not None:
                from gpiozero import Button
                self.sw = Button(self.sw_pin, pull_up=True, bounce_time=0.1)
                self.sw.when_pressed = self._on_switch_press
                logger.info(f"Rotary encoder switch initialized: GPIO{self.sw_pin}")
            
        except Exception as e:
            logger.error(f"Error setting up rotary encoder: {e}")
            raise
    
    def _on_clk_change(self):
        """Handle CLK pin state change (rotation detection)."""
        self._process_rotation()
    
    def _on_dt_change(self):
        """Handle DT pin state change (rotation detection)."""
        self._process_rotation()
    
    def _process_rotation(self):
        """Process rotation detection with proper quadrature decoding and rate limiting."""
        import time
        current_time = time.time()
        
        # Rate limiting - ignore if too soon since last rotation
        if current_time - self._last_rotation_time < self._min_rotation_interval:
            return
        
        with self.rotation_lock:
            clk_state = self.clk.value
            dt_state = self.dt.value
            
            # Initialize last states if not set
            if self.clk_last_state is None:
                self.clk_last_state = clk_state
                self.dt_last_state = dt_state
                return
            
            # Only process if CLK state changed (primary signal for rotation)
            if clk_state == self.clk_last_state:
                # CLK didn't change, just update DT state if it changed
                if dt_state != self.dt_last_state:
                    self.dt_last_state = dt_state
                return
            
            # CLK changed - this is a valid rotation step
            # Determine direction based on DT state relative to CLK
            if dt_state != clk_state:
                # Clockwise: DT is opposite of CLK when CLK changes
                self._rotate_clockwise()
                self._last_rotation_time = current_time
            else:
                # Counter-clockwise: DT matches CLK when CLK changes
                self._rotate_counterclockwise()
                self._last_rotation_time = current_time
            
            # Update last states
            self.clk_last_state = clk_state
            self.dt_last_state = dt_state
    
    def _rotate_clockwise(self):
        """Handle clockwise rotation (volume up)."""
        logger.debug("Rotary encoder: clockwise rotation (volume up)")
        self.volume_controller.adjust_volume(self.volume_step)
        current_volume = self.volume_controller.get_volume()
        
        if self.on_volume_change:
            try:
                self.on_volume_change(current_volume)
            except Exception as e:
                logger.error(f"Error in volume change callback: {e}")
    
    def _rotate_counterclockwise(self):
        """Handle counter-clockwise rotation (volume down)."""
        logger.debug("Rotary encoder: counter-clockwise rotation (volume down)")
        self.volume_controller.adjust_volume(-self.volume_step)
        current_volume = self.volume_controller.get_volume()
        
        if self.on_volume_change:
            try:
                self.on_volume_change(current_volume)
            except Exception as e:
                logger.error(f"Error in volume change callback: {e}")
    
    def _on_switch_press(self):
        """Handle switch/button press (mute toggle)."""
        logger.info("Rotary encoder switch pressed - toggling mute")
        self.volume_controller.toggle_mute()
        
        if self.on_mute_toggle:
            try:
                self.on_mute_toggle()
            except Exception as e:
                logger.error(f"Error in mute toggle callback: {e}")
    
    def close(self):
        """Clean up GPIO resources."""
        if self.clk:
            self.clk.close()
        if self.dt:
            self.dt.close()
        if self.sw:
            self.sw.close()
        # Close volume controller to stop time-based limiting thread
        if self.volume_controller:
            self.volume_controller.close()
        logger.info("Rotary encoder closed")
    
    def wait(self):
        """Wait for encoder input (blocks forever)."""
        logger.info("Rotary encoder waiting for input...")
        pause()


