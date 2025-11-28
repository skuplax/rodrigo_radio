"""Main player controller orchestrating buttons, sources, and backends."""
import logging
import time
import threading
import socket
from typing import Optional
from hardware.buttons import ButtonHandler
from core.sources import SourceManager
from core.playback_history import PlaybackHistory
from backends.youtube_backend import YouTubeBackend
from backends.spotify_backend import SpotifyBackend
from backends.base import BaseBackend, BackendError
from hardware.rotary_encoder import RotaryEncoder
from utils.announcements import announce_source
from utils.sound_feedback import (
    play_startup_beep,
    play_connection_error_beep,
    play_network_error_beep,
    play_retry_beep,
    play_no_sources_beep,
    DelayedBeep,
    play_fetching_beep
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2  # Skip to next source after 2 failed attempts
RETRY_SLEEP = 2.0  # seconds
NETWORK_CHECK_TIMEOUT = 30  # Maximum seconds to wait for network on startup
NETWORK_CHECK_INTERVAL = 1.0  # Seconds between network connectivity checks


class PlayerController:
    """Main controller for the music player."""
    
    def __init__(self, sources_file=None, state_file=None, history_file=None, 
                 button_pins=None, encoder_pins=None):
        """
        Initialize the player controller.
        
        Args:
            sources_file: Path to sources.json (optional)
            state_file: Path to state.json (optional)
            history_file: Path to history.json (optional)
            button_pins: Dictionary of button pins (optional)
            encoder_pins: Dictionary with 'clk', 'dt', and optionally 'sw' pins for rotary encoder (optional)
        """
        self.source_manager = SourceManager(sources_file, state_file)
        self.history = PlaybackHistory(history_file)
        self.button_handler = ButtonHandler(button_pins)
        
        self.current_backend: Optional[BaseBackend] = None
        self.current_source: Optional[dict] = None
        self._lock = threading.RLock()  # Use reentrant lock to allow nested lock acquisition
        self._cancel_retry = threading.Event()  # Event to cancel ongoing retry attempts
        self._active_retry_thread: Optional[threading.Thread] = None  # Track active retry thread
        self._target_source: Optional[dict] = None  # Track which source we're currently trying to play
        
        # Backend instances - reuse instead of recreating
        self._spotify_backend: Optional[SpotifyBackend] = None
        self._youtube_backend: Optional[YouTubeBackend] = None
        
        # Set up rotary encoder if pins provided
        self.rotary_encoder: Optional[RotaryEncoder] = None
        if encoder_pins:
            try:
                self.rotary_encoder = RotaryEncoder(
                    clk_pin=encoder_pins.get('clk'),
                    dt_pin=encoder_pins.get('dt'),
                    sw_pin=encoder_pins.get('sw'),
                    volume_step=encoder_pins.get('volume_step', 2)
                )
                # Set up callbacks for volume changes
                self.rotary_encoder.on_volume_change = self._on_volume_change
                self.rotary_encoder.on_mute_toggle = self._on_mute_toggle
                logger.info("Rotary encoder initialized for volume control")
            except Exception as e:
                logger.error(f"Failed to initialize rotary encoder: {e}")
        
        # Register button callbacks
        self._setup_buttons()
        
        # Play startup beep
        play_startup_beep()
        
        # Auto-start playback if we have a current source
        self._auto_start()
    
    def _setup_buttons(self):
        """Register button callbacks."""
        self.button_handler.register_callback('play_pause', self._on_play_pause)
        self.button_handler.register_callback('previous', self._on_previous)
        self.button_handler.register_callback('next', self._on_next)
        self.button_handler.register_callback('cycle_source', self._on_cycle_source)
        logger.info("Button callbacks registered")
    
    def _get_backend_for_source(self, source: dict) -> BaseBackend:
        """
        Get the appropriate backend for a source type.
        Reuses existing backend instances instead of creating new ones.
        
        Args:
            source: Source dictionary
            
        Returns:
            Backend instance (reused if available)
        """
        source_type = source.get('type')
        
        if source_type == 'spotify_playlist':
            if self._spotify_backend is None:
                self._spotify_backend = SpotifyBackend()
                logger.info("Created Spotify backend instance (will be reused)")
            return self._spotify_backend
        elif source_type in ('youtube_channel', 'youtube_playlist'):
            if self._youtube_backend is None:
                self._youtube_backend = YouTubeBackend()
                logger.info("Created YouTube backend instance (will be reused)")
            return self._youtube_backend
        else:
            raise ValueError(f"Unknown source type: {source_type}")
    
    def _play_source_with_retry(self, source: dict) -> bool:
        """
        Play a source with retry logic.
        
        Args:
            source: Source dictionary
            
        Returns:
            True if playback started successfully
        """
        source_type = source.get('type')
        source_id = source.get('id')
        label = source.get('label', source_id)
        
        logger.info(f"Attempting to play source: {label} (type: {source_type})")
        
        # Check if this source is still the target (might have been cancelled)
        with self._lock:
            if self._target_source != source:
                logger.info(f"Source {label} is no longer the target, cancelling retry")
                return False
        
        # Clear any previous cancel flag
        self._cancel_retry.clear()
        
        # Start delayed beep for fetching (only plays if operation takes >1s)
        with DelayedBeep(play_fetching_beep, delay=1.0) as delayed_beep:
            for attempt in range(1, MAX_RETRIES + 1):
                # Check if retry was cancelled (e.g., user pressed cycle source)
                if self._cancel_retry.is_set():
                    logger.info(f"Retry cancelled for {label} (user requested new source)")
                    return False
                
                # Check if source is still the target
                with self._lock:
                    if self._target_source != source:
                        logger.info(f"Source {label} is no longer the target, cancelling retry")
                        return False
                
                try:
                    # Get appropriate backend
                    backend = self._get_backend_for_source(source)
                    
                    # Prepare kwargs based on source type
                    kwargs = {'source_type': source_type}
                    
                    if source_type == 'spotify_playlist':
                        kwargs['playlist_id'] = source.get('playlist_id')
                        source_id_to_play = kwargs['playlist_id'] or source_id
                    elif source_type == 'youtube_channel':
                        kwargs['channel_id'] = source.get('channel_id')
                        source_id_to_play = kwargs['channel_id'] or source_id
                    elif source_type == 'youtube_playlist':
                        kwargs['playlist_id'] = source.get('playlist_id')
                        source_id_to_play = kwargs['playlist_id'] or source_id
                    else:
                        logger.error(f"Unknown source type: {source_type}")
                        return False
                    
                    # Attempt to play
                    success = backend.play(source_id_to_play, **kwargs)
                    
                    if success:
                        # Check again if this source is still the target before setting it
                        with self._lock:
                            if self._target_source != source:
                                logger.info(f"Source {label} is no longer the target, stopping backend")
                                try:
                                    backend.stop()
                                except Exception as e:
                                    logger.warning(f"Error stopping cancelled backend: {e}")
                                return False
                            
                            # Stop old backend and set new one (need lock for this)
                            old_backend = self.current_backend
                            # Set new backend and source first
                            self.current_backend = backend
                            self.current_source = source
                            self._target_source = None  # Clear target since we succeeded
                            
                            # Then stop old backend (after setting new one to avoid race condition)
                            if old_backend and old_backend != backend:
                                try:
                                    old_backend.stop()
                                except Exception as e:
                                    logger.warning(f"Error stopping old backend: {e}")
                        
                        # Log playback start (outside lock to avoid blocking)
                        item_name = backend.get_current_item()
                        with self._lock:
                            self.history.log_playback_start(source, item_name)
                        
                        logger.info(f"Successfully started playback: {label}")
                        # Cancel delayed beep since operation completed quickly
                        delayed_beep.cancel()
                        return True
                    else:
                        raise BackendError("Backend returned False")
                        
                except (BackendError, ConnectionError, TimeoutError) as e:
                    # Cancel delayed beep since we're handling the error
                    delayed_beep.cancel()
                    
                    # Determine error type and play appropriate beep
                    error_str = str(e).lower()
                    if 'network' in error_str or 'connection' in error_str or 'timeout' in error_str:
                        play_network_error_beep()
                    elif 'not found' in error_str or '404' in error_str:
                        # Not found errors are handled by backends, but play connection error as fallback
                        play_connection_error_beep()
                    else:
                        play_connection_error_beep()
                    
                    logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed for {label}: {e}")
                    
                    if attempt < MAX_RETRIES:
                        logger.info(f"Retrying in {RETRY_SLEEP} seconds...")
                        play_retry_beep()
                        time.sleep(RETRY_SLEEP)
                    else:
                        logger.error(f"Failed to play {label} after {MAX_RETRIES} attempts")
                        return False
                except Exception as e:
                    # Cancel delayed beep since we're handling the error
                    delayed_beep.cancel()
                    
                    # Check if it's a network-related error
                    error_str = str(e).lower()
                    error_type = type(e).__name__.lower()
                    
                    if any(keyword in error_str or keyword in error_type for keyword in 
                           ['network', 'connection', 'timeout', 'dns', 'socket', 'urlerror']):
                        play_network_error_beep()
                    else:
                        play_connection_error_beep()
                    
                    logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed for {label}: {e}")
                    
                    if attempt < MAX_RETRIES:
                        logger.info(f"Retrying in {RETRY_SLEEP} seconds...")
                        play_retry_beep()
                        time.sleep(RETRY_SLEEP)
                    else:
                        logger.error(f"Failed to play {label} after {MAX_RETRIES} attempts")
                        return False
        
        return False
    
    def _switch_source(self, source: dict):
        """
        Switch to a new source.
        Runs retry logic in background thread to avoid blocking button input.
        
        Args:
            source: Source dictionary to switch to
        """
        # Cancel any existing retry attempts
        self._cancel_retry.set()
        
        # Wait for previous retry thread to acknowledge cancellation (brief wait)
        if self._active_retry_thread and self._active_retry_thread.is_alive():
            logger.info("Waiting for previous retry thread to cancel...")
            time.sleep(0.1)  # Brief wait for thread to check cancellation
        
        # Note: Current backend should already be stopped by _on_cycle_source
        # But we'll capture reference for cleanup after new one starts
        old_backend = None
        old_backend_type = None
        with self._lock:
            if self.current_backend:
                old_backend = self.current_backend
                old_backend_type = type(old_backend).__name__
                # Double-check it's stopped (should already be stopped, but ensure it)
                try:
                    if hasattr(old_backend, 'is_playing') and old_backend.is_playing():
                        old_backend.stop()
                        logger.info(f"Ensured old backend ({old_backend_type}) is stopped")
                except Exception as e:
                    logger.debug(f"Old backend already stopped or error: {e}")
            
            # Set new target source
            self._target_source = source
        
        # Give a brief moment for stop to complete (especially for Spotify)
        if old_backend:
            if old_backend_type == 'SpotifyBackend':
                time.sleep(0.3)  # Reduced since we already stopped it
            else:
                time.sleep(0.1)  # Reduced since we already stopped it
        
        # Run retry logic in background thread so it doesn't block button input
        def retry_in_background():
            # Store reference to old backend for cleanup after new one starts
            captured_old_backend = old_backend
            
            success = self._play_source_with_retry(source)
            
            if not success:
                # Check if cancelled FIRST
                if self._cancel_retry.is_set():
                    logger.info(f"Retry cancelled for {source.get('label')}, not trying next source")
                    return
                
                # Check if source is still the target
                with self._lock:
                    if self._target_source != source:
                        logger.info(f"Source {source.get('label')} is no longer the target, not trying next source")
                        return
                
                # If failed and not cancelled, just log the failure and stop
                # Don't automatically try next source - let user manually cycle if they want
                logger.warning(f"Failed to play {source.get('label')} after all retries. User can manually cycle to next source if desired.")
            else:
                # Ensure old backend is fully stopped (double-check)
                # But only if it's different from the new backend (same source = same backend instance)
                if captured_old_backend:
                    with self._lock:
                        # Check if old backend is different from current backend
                        # (if cycling to same source, they're the same instance)
                        if self.current_backend != captured_old_backend:
                            try:
                                captured_old_backend.stop()
                                logger.info("Double-checked old backend is stopped")
                            except Exception as e:
                                logger.debug(f"Old backend already stopped or error: {e}")
                        else:
                            logger.debug("Old backend is same as new backend (same source), skipping double-stop")
                
                # Log source change
                with self._lock:
                    self.history.log_source_change(source)
            
            # Clear active thread reference
            with self._lock:
                if self._active_retry_thread == threading.current_thread():
                    self._active_retry_thread = None
        
        # Start retry in background thread
        thread = threading.Thread(target=retry_in_background, daemon=True)
        with self._lock:
            self._active_retry_thread = thread
        thread.start()
    
    def _check_network_connectivity(self) -> bool:
        """
        Check if network connectivity is available by attempting DNS resolution.
        
        Returns:
            True if network appears to be available, False otherwise
        """
        try:
            # Try to resolve a well-known domain name (tests DNS resolution)
            socket.gethostbyname('google.com')
            return True
        except (socket.gaierror, OSError):
            return False
    
    def _wait_for_network(self, timeout: float = NETWORK_CHECK_TIMEOUT) -> bool:
        """
        Wait for network connectivity to become available.
        
        Args:
            timeout: Maximum seconds to wait
            
        Returns:
            True if network became available, False if timeout
        """
        start_time = time.time()
        logger.info("Waiting for network connectivity before auto-start...")
        
        while time.time() - start_time < timeout:
            if self._check_network_connectivity():
                elapsed = time.time() - start_time
                logger.info(f"Network connectivity available after {elapsed:.1f} seconds")
                return True
            time.sleep(NETWORK_CHECK_INTERVAL)
        
        logger.warning(f"Network connectivity check timed out after {timeout} seconds")
        return False
    
    def _auto_start(self):
        """Auto-start playback on initialization if we have a current source."""
        current_source = self.source_manager.get_current_source()
        if current_source:
            # Check if source requires network (YouTube or Spotify)
            source_type = current_source.get('type', '')
            requires_network = source_type in ('youtube_channel', 'youtube_playlist', 'spotify_playlist')
            
            if requires_network:
                # Wait for network before auto-starting
                if not self._wait_for_network():
                    logger.warning("Network not available, skipping auto-start. User can manually start playback.")
                    return
            
            # Announce the source before starting
            source_label = current_source.get('label', 'Unknown source')
            announce_source(source_label)
            
            logger.info("Auto-starting playback from saved state")
            self._switch_source(current_source)
        else:
            logger.info("No current source, waiting for user input")
    
    def _on_play_pause(self):
        """Handle play/pause button press."""
        logger.info("Play/pause button callback invoked")
        with self._lock:
            if not self.current_backend:
                logger.info("No backend available, attempting to start current source")
                # No backend, try to start current source
                current_source = self.source_manager.get_current_source()
                if current_source:
                    self._switch_source(current_source)
                else:
                    logger.warning("No current source available to start")
                return
            
            try:
                is_playing = self.current_backend.is_playing()
                logger.info(f"Backend playing state: {is_playing}")
                
                if is_playing:
                    # Pause
                    logger.info("Attempting to pause playback")
                    if self.current_backend.pause():
                        self.history.log_action('pause')
                        logger.info("Playback paused")
                    else:
                        logger.warning("Pause command returned False")
                else:
                    # Resume or start
                    logger.info("Attempting to resume playback")
                    if self.current_backend.resume():
                        self.history.log_action('resume')
                        logger.info("Playback resumed")
                    else:
                        logger.warning("Resume command returned False, trying to restart source")
                        # Try to restart current source
                        if self.current_source:
                            self._switch_source(self.current_source)
                        else:
                            logger.warning("No current source to restart")
            except Exception as e:
                logger.error(f"Error in play/pause callback: {e}", exc_info=True)
    
    def _on_previous(self):
        """Handle previous button press."""
        with self._lock:
            if not self.current_backend:
                return
            
            if self.current_backend.previous():
                self.history.log_action('previous')
                # Update current item in history
                item_name = self.current_backend.get_current_item()
                if item_name and self.current_source:
                    self.history.log_playback_start(self.current_source, item_name)
                logger.info("Previous track")
                
                # Resume playback if paused (like a normal music player)
                if not self.current_backend.is_playing():
                    if self.current_backend.resume():
                        logger.info("Resumed playback after previous track")
                    else:
                        logger.warning("Failed to resume playback after previous track")
            else:
                logger.warning("Previous track not available")
    
    def _on_next(self):
        """Handle next button press."""
        with self._lock:
            if not self.current_backend:
                return
            
            if self.current_backend.next():
                self.history.log_action('next')
                # Update current item in history
                item_name = self.current_backend.get_current_item()
                if item_name and self.current_source:
                    self.history.log_playback_start(self.current_source, item_name)
                logger.info("Next track")
                
                # Resume playback if paused (like a normal music player)
                if not self.current_backend.is_playing():
                    if self.current_backend.resume():
                        logger.info("Resumed playback after next track")
                    else:
                        logger.warning("Failed to resume playback after next track")
            else:
                logger.warning("Next track not available")
    
    def _on_cycle_source(self):
        """Handle cycle source button press."""
        cycle_start = time.perf_counter()
        logger.info("Cycling to next source")
        # Cancel any ongoing retry attempts
        self._cancel_retry.set()
        
        # Clear target source to cancel any in-flight retry attempts
        with self._lock:
            self._target_source = None
        
        # Get next source first to check if it's the same
        source_cycle_start = time.perf_counter()
        new_source = self.source_manager.cycle_source()
        source_cycle_time = time.perf_counter() - source_cycle_start
        if not new_source:
            logger.warning("No sources available to cycle")
            play_no_sources_beep()
            return
        
        # Check if new source is the same as current source
        with self._lock:
            is_same_source = (self.current_source and 
                            self.current_source.get('id') == new_source.get('id') and
                            self.current_source.get('type') == new_source.get('type'))
        
        # Only stop current playback if switching to a different source
        stop_start = time.perf_counter()
        if not is_same_source:
            with self._lock:
                if self.current_backend:
                    try:
                        self.current_backend.stop()
                        logger.info("Stopped current playback immediately on cycle")
                    except Exception as e:
                        logger.warning(f"Error stopping current backend: {e}")
        else:
            logger.info("Cycling to same source, not stopping current playback")
        stop_time = time.perf_counter() - stop_start
        
        # Announce the source
        announce_start = time.perf_counter()
        source_label = new_source.get('label', 'Unknown source')
        announce_source(source_label)
        announce_time = time.perf_counter() - announce_start
        
        # Then try to switch to it
        switch_start = time.perf_counter()
        self._switch_source(new_source)
        switch_time = time.perf_counter() - switch_start
        
        # Benchmark logging
        log_start = time.perf_counter()
        total_cycle_time = time.perf_counter() - cycle_start
        source_type = new_source.get('type', 'unknown')
        if source_type == 'youtube_channel' or source_type == 'youtube_playlist':
            logger.info(f"[BENCHMARK] YouTube cycle total: {total_cycle_time*1000:.2f}ms | "
                       f"source_cycle: {source_cycle_time*1000:.2f}ms | "
                       f"stop: {stop_time*1000:.2f}ms | "
                       f"announce: {announce_time*1000:.2f}ms | "
                       f"switch: {switch_time*1000:.2f}ms")
        log_time = time.perf_counter() - log_start
        if source_type == 'youtube_channel' or source_type == 'youtube_playlist':
            logger.info(f"[BENCHMARK] Logging overhead: {log_time*1000:.2f}ms")
    
    def reload_sources(self) -> bool:
        """
        Manually reload sources from file if it has changed.
        Does not disrupt current playback.
        
        Returns:
            True if sources were reloaded, False if no changes
        """
        with self._lock:
            was_reloaded = self.source_manager.reload_sources(preserve_current=True)
            if was_reloaded:
                # Update current_source reference if it changed
                new_current = self.source_manager.get_current_source()
                if new_current and (not self.current_source or 
                                   new_current.get('id') != self.current_source.get('id')):
                    logger.info("Current source reference updated after reload")
                    # Note: We don't change current_source here to avoid disrupting playback
                    # It will be updated on next cycle or when switching sources
            return was_reloaded
    
    def get_status(self) -> dict:
        """
        Get current player status.
        
        Returns:
            Dictionary with status information
        """
        with self._lock:
            # Check for source changes (non-disruptive)
            self.source_manager.reload_sources(preserve_current=True)
            
            status = {
                'playing': False,
                'source': None,
                'current_item': None,
                'source_type': None
            }
            
            if self.current_backend:
                status['playing'] = self.current_backend.is_playing()
                status['current_item'] = self.current_backend.get_current_item()
            
            if self.current_source:
                status['source'] = self.current_source.get('label')
                status['source_type'] = self.current_source.get('type')
                status['source_id'] = self.current_source.get('id')
            
            return status
    
    def run(self):
        """Run the controller (blocks forever waiting for button presses)."""
        logger.info("Player controller running, waiting for button input...")
        self.button_handler.wait()
    
    def _on_volume_change(self, volume: int):
        """Handle volume change from rotary encoder."""
        logger.info(f"Volume changed to {volume}%")
        # Could add TTS announcement here if desired
        # announce_volume(volume)
    
    def _on_mute_toggle(self):
        """Handle mute toggle from rotary encoder switch."""
        logger.info("Mute toggled")
        # Could add TTS announcement here if desired
        # announce_mute_state()
    
    def shutdown(self):
        """Gracefully shutdown the controller."""
        logger.info("Shutting down player controller...")
        with self._lock:
            if self.current_backend:
                try:
                    self.current_backend.stop()
                except Exception as e:
                    logger.error(f"Error stopping backend during shutdown: {e}")
            
            # Stop backend instances (they'll be cleaned up)
            if self._spotify_backend:
                try:
                    self._spotify_backend.stop()
                except Exception as e:
                    logger.debug(f"Error stopping Spotify backend during shutdown: {e}")
            if self._youtube_backend:
                try:
                    self._youtube_backend.stop()
                except Exception as e:
                    logger.debug(f"Error stopping YouTube backend during shutdown: {e}")
        
        # Clean up rotary encoder
        if self.rotary_encoder:
            try:
                self.rotary_encoder.close()
            except Exception as e:
                logger.error(f"Error closing rotary encoder: {e}")
        
        logger.info("Player controller shutdown complete")

