"""Source configuration and state management."""
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Default paths - use current working directory if script is in music-player directory
# Otherwise fall back to /home/pi/music-player for backwards compatibility
_SCRIPT_DIR = Path(__file__).parent.absolute()
# If we're in a subdirectory (core/, hardware/, etc.), go up to project root
if _SCRIPT_DIR.name in ("core", "hardware", "utils", "scripts", "backends"):
    _BASE_DIR = _SCRIPT_DIR.parent
elif _SCRIPT_DIR.name == "music-player" or (_SCRIPT_DIR / "config" / "sources.json.example").exists():
    _BASE_DIR = _SCRIPT_DIR
else:
    _BASE_DIR = Path("/home/pi/music-player")

DEFAULT_SOURCES_FILE = _BASE_DIR / "config" / "sources.json"
DEFAULT_STATE_FILE = _BASE_DIR / "data" / "state.json"


class SourceManager:
    """Manages audio sources and current state."""
    
    def __init__(self, sources_file: Path = None, state_file: Path = None):
        self.sources_file = sources_file or DEFAULT_SOURCES_FILE
        self.state_file = state_file or DEFAULT_STATE_FILE
        self._sources: List[Dict] = []
        self._current_index = 0
        self._last_file_mtime = 0  # Track file modification time for hot-reload
        self._load_sources()
        self._load_state()
    
    def _load_sources(self):
        """Load sources from JSON file."""
        try:
            if not self.sources_file.exists():
                logger.warning(f"Sources file not found: {self.sources_file}")
                self._sources = []
                self._last_file_mtime = 0
                return
            
            # Update modification time tracking
            try:
                self._last_file_mtime = self.sources_file.stat().st_mtime
            except Exception:
                self._last_file_mtime = 0
            
            with open(self.sources_file, 'r') as f:
                self._sources = json.load(f)
            
            if not isinstance(self._sources, list):
                logger.error("Sources file must contain a JSON array")
                self._sources = []
                return
            
            logger.info(f"Loaded {len(self._sources)} sources")
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in sources file: {e}")
            self._sources = []
        except Exception as e:
            logger.error(f"Error loading sources: {e}")
            self._sources = []
    
    def _has_file_changed(self) -> bool:
        """Check if sources file has been modified since last load."""
        try:
            if not self.sources_file.exists():
                return False
            
            current_mtime = self.sources_file.stat().st_mtime
            return current_mtime > self._last_file_mtime
        except Exception:
            return False
    
    def reload_sources(self, preserve_current: bool = True) -> bool:
        """
        Reload sources from file if it has changed.
        
        Args:
            preserve_current: If True, try to preserve current source after reload
            
        Returns:
            True if sources were reloaded, False if no changes detected
        """
        if not self._has_file_changed():
            return False
        
        # Save current source info before reload
        current_source = None
        current_source_id = None
        if preserve_current and self._sources and 0 <= self._current_index < len(self._sources):
            current_source = self._sources[self._current_index]
            current_source_id = current_source.get('id')
            logger.debug(f"Preserving current source: {current_source.get('label', current_source_id)}")
        
        # Reload sources
        old_count = len(self._sources)
        self._load_sources()
        new_count = len(self._sources)
        
        if old_count != new_count:
            logger.info(f"Sources reloaded: {old_count} -> {new_count} sources")
        else:
            logger.info(f"Sources reloaded: {new_count} sources (count unchanged)")
        
        # Try to restore current source if preserve_current is True
        if preserve_current and current_source_id and self._sources:
            # Find the source with the same ID
            found_index = None
            for i, source in enumerate(self._sources):
                if source.get('id') == current_source_id:
                    found_index = i
                    break
            
            if found_index is not None:
                self._current_index = found_index
                logger.info(f"Preserved current source at index {found_index}: {self._sources[found_index].get('label', current_source_id)}")
            else:
                # Current source was removed, reset to first source
                if self._sources:
                    self._current_index = 0
                    logger.warning(
                        f"Current source '{current_source_id}' was removed from sources. "
                        f"Switched to first source: {self._sources[0].get('label', 'unknown')}"
                    )
                else:
                    self._current_index = 0
                    logger.warning("All sources removed, reset to index 0")
            
            # Save updated state
            self.save_state()
        
        return True
    
    def _load_state(self):
        """Load current state from JSON file."""
        try:
            if not self.state_file.exists():
                logger.info("State file not found, starting with first source")
                self._current_index = 0
                return
            
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            index = state.get('current_source_index', 0)
            if 0 <= index < len(self._sources):
                self._current_index = index
                logger.info(f"Restored state: source index {index}")
            else:
                logger.warning(f"Invalid source index {index}, resetting to 0")
                self._current_index = 0
                
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            self._current_index = 0
    
    def save_state(self):
        """Save current state to JSON file."""
        try:
            state = {
                'current_source_index': self._current_index,
                'last_updated': datetime.now().isoformat()
            }
            
            # Ensure directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            logger.debug(f"Saved state: source index {self._current_index}")
            
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def get_sources(self) -> List[Dict]:
        """Get all configured sources."""
        return self._sources.copy()
    
    def get_current_source(self, check_for_changes: bool = False) -> Optional[Dict]:
        """
        Get the currently selected source.
        
        Args:
            check_for_changes: If True, check for file changes and reload if needed
        """
        if check_for_changes:
            self.reload_sources(preserve_current=True)
        
        if not self._sources or self._current_index >= len(self._sources):
            return None
        return self._sources[self._current_index]
    
    def cycle_source(self) -> Dict:
        """Cycle to the next source and return it."""
        # Check for file changes before cycling (hot-reload)
        self.reload_sources(preserve_current=True)
        
        if not self._sources:
            logger.warning("No sources configured")
            return None
        
        self._current_index = (self._current_index + 1) % len(self._sources)
        self.save_state()
        
        current = self.get_current_source()
        logger.info(f"Cycled to source: {current.get('label', current.get('id', 'unknown'))}")
        return current
    
    def get_source_count(self) -> int:
        """Get the number of configured sources."""
        return len(self._sources)

