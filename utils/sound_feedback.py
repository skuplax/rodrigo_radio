"""Sound feedback using beep tones for system events."""
import logging
import math
import struct
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

# Default audio settings
SAMPLE_RATE = 44100
DEFAULT_VOLUME = 0.2  # 50% volume


def _generate_beep_wav(frequency: float, duration: float, volume: float = DEFAULT_VOLUME) -> bytes:
    """
    Generate WAV file data for a beep tone.
    
    Args:
        frequency: Frequency in Hz
        duration: Duration in seconds
        volume: Volume level (0.0 to 1.0)
        
    Returns:
        WAV file data as bytes
    """
    num_samples = int(SAMPLE_RATE * duration)
    
    # Generate sine wave samples
    samples = []
    for i in range(num_samples):
        t = float(i) / SAMPLE_RATE
        sample = math.sin(2.0 * math.pi * frequency * t)
        # Apply volume and convert to 16-bit integer
        sample = int(sample * volume * 32767)
        samples.append(sample)
    
    # Convert to bytes (little-endian 16-bit signed integers)
    sample_data = struct.pack('<' + 'h' * len(samples), *samples)
    
    # WAV file header
    # RIFF header
    riff_header = b'RIFF'
    file_size = 36 + len(sample_data)
    riff_size = struct.pack('<I', file_size)
    wave_format = b'WAVE'
    
    # fmt chunk
    fmt_chunk_id = b'fmt '
    fmt_chunk_size = struct.pack('<I', 16)  # PCM format chunk size
    audio_format = struct.pack('<H', 1)  # PCM
    num_channels = struct.pack('<H', 1)  # Mono
    sample_rate = struct.pack('<I', SAMPLE_RATE)
    byte_rate = struct.pack('<I', SAMPLE_RATE * 2)  # sample_rate * num_channels * bits_per_sample/8
    block_align = struct.pack('<H', 2)  # num_channels * bits_per_sample/8
    bits_per_sample = struct.pack('<H', 16)
    
    # data chunk
    data_chunk_id = b'data'
    data_chunk_size = struct.pack('<I', len(sample_data))
    
    # Combine all parts
    wav_data = (riff_header + riff_size + wave_format +
                fmt_chunk_id + fmt_chunk_size + audio_format + num_channels +
                sample_rate + byte_rate + block_align + bits_per_sample +
                data_chunk_id + data_chunk_size + sample_data)
    
    return wav_data


def _generate_ascending_beep(start_freq: float, end_freq: float, duration: float, volume: float = DEFAULT_VOLUME) -> bytes:
    """
    Generate WAV file data for an ascending beep (frequency sweep).
    
    Args:
        start_freq: Starting frequency in Hz
        end_freq: Ending frequency in Hz
        duration: Duration in seconds
        volume: Volume level (0.0 to 1.0)
        
    Returns:
        WAV file data as bytes
    """
    num_samples = int(SAMPLE_RATE * duration)
    samples = []
    
    for i in range(num_samples):
        t = float(i) / SAMPLE_RATE
        # Linear frequency sweep
        freq = start_freq + (end_freq - start_freq) * (t / duration)
        sample = math.sin(2.0 * math.pi * freq * t)
        sample = int(sample * volume * 32767)
        samples.append(sample)
    
    sample_data = struct.pack('<' + 'h' * len(samples), *samples)
    
    # WAV header (same as _generate_beep_wav)
    file_size = 36 + len(sample_data)
    wav_data = (b'RIFF' + struct.pack('<I', file_size) + b'WAVE' +
                b'fmt ' + struct.pack('<I', 16) + struct.pack('<H', 1) + struct.pack('<H', 1) +
                struct.pack('<I', SAMPLE_RATE) + struct.pack('<I', SAMPLE_RATE * 2) +
                struct.pack('<H', 2) + struct.pack('<H', 16) +
                b'data' + struct.pack('<I', len(sample_data)) + sample_data)
    
    return wav_data


def _generate_descending_beep(start_freq: float, end_freq: float, duration: float, volume: float = DEFAULT_VOLUME) -> bytes:
    """
    Generate WAV file data for a descending beep (frequency sweep).
    
    Args:
        start_freq: Starting frequency in Hz
        end_freq: Ending frequency in Hz
        duration: Duration in seconds
        volume: Volume level (0.0 to 1.0)
        
    Returns:
        WAV file data as bytes
    """
    return _generate_ascending_beep(end_freq, start_freq, duration, volume)


def _play_wav_data(wav_data: bytes):
    """
    Play WAV data using aplay (non-blocking).
    
    Args:
        wav_data: WAV file data as bytes
    """
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
            tmp_file.write(wav_data)
            tmp_path = tmp_file.name
        
        # Play using aplay (non-blocking)
        subprocess.Popen(
            ['aplay', tmp_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Clean up temp file after a delay (give aplay time to read it)
        def cleanup():
            import time
            time.sleep(1.0)  # Wait 1 second before cleanup
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
        
        threading.Thread(target=cleanup, daemon=True).start()
        
    except Exception as e:
        logger.debug(f"Error playing beep sound: {e}")


def play_startup_beep():
    """Play startup beep (ascending: 200Hz → 400Hz, 0.3s)."""
    wav_data = _generate_ascending_beep(200, 400, 0.3)
    _play_wav_data(wav_data)
    logger.debug("Played startup beep")


def play_connection_error_beep():
    """Play connection error beep (two short low beeps: 200Hz, 0.2s each)."""
    wav_data1 = _generate_beep_wav(200, 0.2)
    wav_data2 = _generate_beep_wav(200, 0.2)
    
    # Play first beep
    _play_wav_data(wav_data1)
    
    # Play second beep after a short delay
    def play_second():
        import time
        time.sleep(0.25)  # Small gap between beeps
        _play_wav_data(wav_data2)
    
    threading.Thread(target=play_second, daemon=True).start()
    logger.debug("Played connection error beep")


def play_network_error_beep():
    """Play network error beep (three short beeps: 300Hz, 0.15s each)."""
    wav_data = _generate_beep_wav(300, 0.15)
    
    def play_beeps():
        import time
        for i in range(3):
            _play_wav_data(wav_data)
            if i < 2:  # Don't sleep after last beep
                time.sleep(0.2)  # Gap between beeps
    
    threading.Thread(target=play_beeps, daemon=True).start()
    logger.debug("Played network error beep")


def play_fetching_beep():
    """Play fetching music beep (single medium beep: 350Hz, 0.2s)."""
    wav_data = _generate_beep_wav(350, 0.2)
    _play_wav_data(wav_data)
    logger.debug("Played fetching beep")


def play_auth_error_beep():
    """Play authentication error beep (long low beep: 150Hz, 0.5s)."""
    wav_data = _generate_beep_wav(150, 0.5)
    _play_wav_data(wav_data)
    logger.debug("Played auth error beep")


def play_not_found_beep():
    """Play source not found beep (two descending beeps: 400Hz → 200Hz, 0.2s each)."""
    wav_data1 = _generate_descending_beep(400, 200, 0.2)
    wav_data2 = _generate_descending_beep(400, 200, 0.2)
    
    # Play first beep
    _play_wav_data(wav_data1)
    
    # Play second beep after a short delay
    def play_second():
        import time
        time.sleep(0.25)  # Small gap between beeps
        _play_wav_data(wav_data2)
    
    threading.Thread(target=play_second, daemon=True).start()
    logger.debug("Played not found beep")


def play_device_error_beep():
    """Play device error beep (single low beep: 180Hz, 0.3s)."""
    wav_data = _generate_beep_wav(180, 0.3)
    _play_wav_data(wav_data)
    logger.debug("Played device error beep")


def play_retry_beep():
    """Play retry beep (quick double beep: 400Hz, 0.1s each)."""
    wav_data = _generate_beep_wav(400, 0.1)
    
    # Play first beep
    _play_wav_data(wav_data)
    
    # Play second beep after a very short delay
    def play_second():
        import time
        time.sleep(0.15)  # Small gap between beeps
        _play_wav_data(wav_data)
    
    threading.Thread(target=play_second, daemon=True).start()
    logger.debug("Played retry beep")


def play_no_sources_beep():
    """Play no sources available beep (single medium-low beep: 250Hz, 0.4s)."""
    wav_data = _generate_beep_wav(250, 0.4)
    _play_wav_data(wav_data)
    logger.debug("Played no sources beep")


class PulsingBeep:
    """
    Plays a pulsing beep sound continuously until stopped.
    Useful for indicating loading/fetching operations.
    """
    
    def __init__(self, frequency: float = 300.0, pulse_duration: float = 0.3, 
                 pause_duration: float = 0.3, volume: float = 0.5, tail_duration: float = 3.0):
        """
        Initialize pulsing beep.
        
        Args:
            frequency: Frequency in Hz (default: 300Hz)
            pulse_duration: Duration of each pulse in seconds (default: 0.3s)
            pause_duration: Duration of pause between pulses in seconds (default: 0.3s)
            volume: Volume level (0.0 to 1.0, default: 0.5 for 50% - louder than other beeps)
            tail_duration: Duration to continue pulsing after stop() is called (default: 3.0s)
        """
        self.frequency = frequency
        self.pulse_duration = pulse_duration
        self.pause_duration = pause_duration
        self.volume = volume
        self.tail_duration = tail_duration
        self._active = False
        self._thread: threading.Thread = None
        self._stop_event = threading.Event()
        self._stop_requested = False
        self._stop_time = None
    
    def start(self):
        """Start the pulsing beep in a background thread."""
        if self._active:
            return  # Already running
        
        self._active = True
        self._stop_requested = False
        self._stop_event.clear()
        self._stop_time = None
        self._thread = threading.Thread(target=self._pulse_loop, daemon=True)
        self._thread.start()
        logger.info("Started pulsing beep")  # Changed to info for visibility
    
    def stop(self):
        """Request stop of the pulsing beep (will continue for tail_duration)."""
        if not self._active:
            return
        
        self._stop_requested = True
        self._stop_time = time.time()
        logger.debug(f"Stop requested for pulsing beep, will continue for {self.tail_duration}s tail")
    
    def _force_stop(self):
        """Force immediate stop of the pulsing beep."""
        self._active = False
        self._stop_requested = True
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)  # Wait up to 1 second for thread to finish
        logger.info("Force stopped pulsing beep")
    
    def _pulse_loop(self):
        """Internal method that runs the pulsing loop."""
        pulse_count = 0
        while self._active and not self._stop_event.is_set():
            # Check if stop was requested and tail duration has elapsed
            if self._stop_requested and self._stop_time:
                elapsed = time.time() - self._stop_time
                if elapsed >= self.tail_duration:
                    # Tail duration elapsed, actually stop
                    self._active = False
                    logger.info(f"Pulsing beep tail completed after {elapsed:.1f}s, stopping (played {pulse_count} pulses)")
                    break
            
            # Generate and play one pulse
            pulse_count += 1
            wav_data = _generate_beep_wav(self.frequency, self.pulse_duration, self.volume)
            _play_wav_data(wav_data)
            logger.debug(f"Playing pulse #{pulse_count} (freq={self.frequency}Hz, vol={self.volume})")
            
            # Wait for pause duration (or until stopped)
            if self._stop_event.wait(self.pause_duration):
                break  # Stop was requested
    
    def __enter__(self):
        """Context manager entry - start pulsing."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - stop pulsing."""
        self.stop()
        return False  # Don't suppress exceptions


class DelayedBeep:
    """
    Context manager for delayed beep feedback.
    Only plays beep if operation takes longer than the delay threshold.
    """
    
    def __init__(self, beep_func, delay: float = 1.0):
        """
        Initialize delayed beep.
        
        Args:
            beep_func: Function to call to play the beep
            delay: Delay in seconds before playing beep (default: 1.0)
        """
        self.beep_func = beep_func
        self.delay = delay
        self.timer: threading.Timer = None
        self.cancelled = False
    
    def __enter__(self):
        """Start the delayed beep timer."""
        self.cancelled = False
        self.timer = threading.Timer(self.delay, self._play_beep)
        self.timer.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cancel the beep if operation completed quickly."""
        self.cancel()
        return False  # Don't suppress exceptions
    
    def cancel(self):
        """Cancel the delayed beep."""
        self.cancelled = True
        if self.timer:
            self.timer.cancel()
            self.timer = None
    
    def _play_beep(self):
        """Internal method to play beep if not cancelled."""
        if not self.cancelled:
            self.beep_func()


