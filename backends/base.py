"""Base backend interface for audio playback backends."""
from abc import ABC, abstractmethod
from typing import Optional, Callable


class BackendError(Exception):
    """Base exception for backend errors."""
    pass


class BaseBackend(ABC):
    """Abstract base class for audio playback backends."""
    
    def __init__(self):
        self._is_playing = False
        self._current_item: Optional[str] = None
        self._on_playback_ended: Optional[Callable[[], None]] = None
        self._on_track_changed: Optional[Callable[[str], None]] = None
    
    @abstractmethod
    def play(self, source_id: str, **kwargs) -> bool:
        """
        Start playing from a source.
        
        Args:
            source_id: Identifier for the source (playlist_id, channel_id, etc.)
            **kwargs: Additional backend-specific parameters
            
        Returns:
            True if playback started successfully, False otherwise
            
        Raises:
            BackendError: If playback cannot be started
        """
        pass
    
    @abstractmethod
    def pause(self) -> bool:
        """Pause playback. Returns True if successful."""
        pass
    
    @abstractmethod
    def resume(self) -> bool:
        """Resume playback. Returns True if successful."""
        pass
    
    @abstractmethod
    def stop(self) -> bool:
        """Stop playback completely. Returns True if successful."""
        pass
    
    @abstractmethod
    def next(self) -> bool:
        """Skip to next track/item. Returns True if successful."""
        pass
    
    @abstractmethod
    def previous(self) -> bool:
        """Go to previous track/item. Returns True if successful."""
        pass
    
    def is_playing(self) -> bool:
        """Check if currently playing."""
        return self._is_playing
    
    def get_current_item(self) -> Optional[str]:
        """Get current track/item identifier or name."""
        return self._current_item
    
    def get_playback_info(self) -> Optional[dict]:
        """
        Get current playback position and duration information.
        
        Returns:
            Dictionary with keys:
                - position_ms: Current position in milliseconds (optional)
                - duration_ms: Total duration in milliseconds (optional)
                - position: Current position as formatted string (e.g., "1:23")
                - duration: Total duration as formatted string (e.g., "3:45")
                - progress: Progress percentage (0-100) if both position and duration available
            Returns None if information is not available
        """
        return None
    
    def set_playing_state(self, playing: bool):
        """Update internal playing state."""
        self._is_playing = playing
    
    def set_current_item(self, item: Optional[str]):
        """Update current item identifier."""
        self._current_item = item
    
    def set_on_playback_ended_callback(self, callback: Optional[Callable[[], None]]):
        """
        Set callback to be invoked when playback ends naturally (e.g., playlist finished).
        
        Args:
            callback: Function to call when playback ends, or None to clear callback
        """
        self._on_playback_ended = callback
    
    def _notify_playback_ended(self):
        """Notify that playback has ended naturally (e.g., playlist finished)."""
        if self._on_playback_ended:
            try:
                self._on_playback_ended()
            except Exception as e:
                # Log but don't raise - callback errors shouldn't break backend
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error in playback ended callback: {e}")
    
    def set_on_track_changed_callback(self, callback: Optional[Callable[[str], None]]):
        """
        Set callback to be invoked when the current track changes.
        
        Args:
            callback: Function to call with the new track name when track changes, or None to clear callback
        """
        self._on_track_changed = callback
    
    def _notify_track_changed(self, new_item: str):
        """Notify that the current track has changed."""
        if self._on_track_changed:
            try:
                self._on_track_changed(new_item)
            except Exception as e:
                # Log but don't raise - callback errors shouldn't break backend
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error in track changed callback: {e}")

