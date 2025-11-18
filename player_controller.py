"""Main player controller orchestrating buttons, sources, and backends."""
import logging
import time
import threading
from typing import Optional
from buttons import ButtonHandler
from sources import SourceManager
from playback_history import PlaybackHistory
from backends.youtube_backend import YouTubeBackend
from backends.spotify_backend import SpotifyBackend
from backends.base import BaseBackend, BackendError

logger = logging.getLogger(__name__)

MAX_RETRIES = 4
RETRY_SLEEP = 2.0  # seconds


class PlayerController:
    """Main controller for the music player."""
    
    def __init__(self, sources_file=None, state_file=None, history_file=None, button_pins=None):
        """
        Initialize the player controller.
        
        Args:
            sources_file: Path to sources.json (optional)
            state_file: Path to state.json (optional)
            history_file: Path to history.json (optional)
            button_pins: Dictionary of button pins (optional)
        """
        self.source_manager = SourceManager(sources_file, state_file)
        self.history = PlaybackHistory(history_file)
        self.button_handler = ButtonHandler(button_pins)
        
        self.current_backend: Optional[BaseBackend] = None
        self.current_source: Optional[dict] = None
        self._lock = threading.Lock()
        
        # Register button callbacks
        self._setup_buttons()
        
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
        
        Args:
            source: Source dictionary
            
        Returns:
            Backend instance
        """
        source_type = source.get('type')
        
        if source_type == 'spotify_playlist':
            return SpotifyBackend()
        elif source_type in ('youtube_channel', 'youtube_playlist'):
            return YouTubeBackend()
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
        
        for attempt in range(1, MAX_RETRIES + 1):
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
                    # Stop old backend
                    if self.current_backend:
                        try:
                            self.current_backend.stop()
                        except Exception as e:
                            logger.warning(f"Error stopping old backend: {e}")
                    
                    # Set new backend and source
                    with self._lock:
                        self.current_backend = backend
                        self.current_source = source
                    
                    # Log playback start
                    item_name = backend.get_current_item()
                    self.history.log_playback_start(source, item_name)
                    
                    logger.info(f"Successfully started playback: {label}")
                    return True
                else:
                    raise BackendError("Backend returned False")
                    
            except Exception as e:
                logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed for {label}: {e}")
                
                if attempt < MAX_RETRIES:
                    logger.info(f"Retrying in {RETRY_SLEEP} seconds...")
                    time.sleep(RETRY_SLEEP)
                else:
                    logger.error(f"Failed to play {label} after {MAX_RETRIES} attempts")
                    return False
        
        return False
    
    def _switch_source(self, source: dict):
        """
        Switch to a new source.
        
        Args:
            source: Source dictionary to switch to
        """
        with self._lock:
            # Stop current playback
            if self.current_backend:
                try:
                    self.current_backend.stop()
                except Exception as e:
                    logger.warning(f"Error stopping current backend: {e}")
            
            # Try to play new source
            success = self._play_source_with_retry(source)
            
            if not success:
                # If failed, try next source
                logger.warning(f"Failed to play {source.get('label')}, trying next source...")
                next_source = self.source_manager.cycle_source()
                if next_source and next_source != source:
                    self._play_source_with_retry(next_source)
            else:
                # Log source change
                self.history.log_source_change(source)
    
    def _auto_start(self):
        """Auto-start playback on initialization if we have a current source."""
        current_source = self.source_manager.get_current_source()
        if current_source:
            logger.info("Auto-starting playback from saved state")
            self._switch_source(current_source)
        else:
            logger.info("No current source, waiting for user input")
    
    def _on_play_pause(self):
        """Handle play/pause button press."""
        with self._lock:
            if not self.current_backend:
                # No backend, try to start current source
                current_source = self.source_manager.get_current_source()
                if current_source:
                    self._switch_source(current_source)
                return
            
            if self.current_backend.is_playing():
                # Pause
                if self.current_backend.pause():
                    self.history.log_action('pause')
                    logger.info("Playback paused")
            else:
                # Resume or start
                if self.current_backend.resume():
                    self.history.log_action('resume')
                    logger.info("Playback resumed")
                else:
                    # Try to restart current source
                    if self.current_source:
                        self._switch_source(self.current_source)
    
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
            else:
                logger.warning("Next track not available")
    
    def _on_cycle_source(self):
        """Handle cycle source button press."""
        logger.info("Cycling to next source")
        new_source = self.source_manager.cycle_source()
        if new_source:
            self._switch_source(new_source)
        else:
            logger.warning("No sources available to cycle")
    
    def get_status(self) -> dict:
        """
        Get current player status.
        
        Returns:
            Dictionary with status information
        """
        with self._lock:
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
    
    def shutdown(self):
        """Gracefully shutdown the controller."""
        logger.info("Shutting down player controller...")
        with self._lock:
            if self.current_backend:
                try:
                    self.current_backend.stop()
                except Exception as e:
                    logger.error(f"Error stopping backend during shutdown: {e}")
        
        logger.info("Player controller shutdown complete")

