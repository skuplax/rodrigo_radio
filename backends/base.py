"""Base backend interface for audio playback backends."""
from abc import ABC, abstractmethod
from typing import Optional


class BackendError(Exception):
    """Base exception for backend errors."""
    pass


class BaseBackend(ABC):
    """Abstract base class for audio playback backends."""
    
    def __init__(self):
        self._is_playing = False
        self._current_item: Optional[str] = None
    
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
    
    def set_playing_state(self, playing: bool):
        """Update internal playing state."""
        self._is_playing = playing
    
    def set_current_item(self, item: Optional[str]):
        """Update current item identifier."""
        self._current_item = item

