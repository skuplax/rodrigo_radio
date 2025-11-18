"""Source configuration and state management."""
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_SOURCES_FILE = Path("/home/pi/music-player/sources.json")
DEFAULT_STATE_FILE = Path("/home/pi/music-player/state.json")


class SourceManager:
    """Manages audio sources and current state."""
    
    def __init__(self, sources_file: Path = None, state_file: Path = None):
        self.sources_file = sources_file or DEFAULT_SOURCES_FILE
        self.state_file = state_file or DEFAULT_STATE_FILE
        self._sources: List[Dict] = []
        self._current_index = 0
        self._load_sources()
        self._load_state()
    
    def _load_sources(self):
        """Load sources from JSON file."""
        try:
            if not self.sources_file.exists():
                logger.warning(f"Sources file not found: {self.sources_file}")
                self._sources = []
                return
            
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
    
    def get_current_source(self) -> Optional[Dict]:
        """Get the currently selected source."""
        if not self._sources or self._current_index >= len(self._sources):
            return None
        return self._sources[self._current_index]
    
    def cycle_source(self) -> Dict:
        """Cycle to the next source and return it."""
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

