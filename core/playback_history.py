"""Playback history logging and retrieval."""
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Default paths - use current working directory if script is in rodrigo_radio directory
# Otherwise fall back to /home/pi/rodrigo_radio for backwards compatibility
_SCRIPT_DIR = Path(__file__).parent.absolute()
# If we're in a subdirectory (core/, hardware/, etc.), go up to project root
if _SCRIPT_DIR.name in ("core", "hardware", "utils", "scripts", "backends"):
    _BASE_DIR = _SCRIPT_DIR.parent
elif _SCRIPT_DIR.name == "rodrigo_radio" or (_SCRIPT_DIR / "config" / "sources.json.example").exists():
    _BASE_DIR = _SCRIPT_DIR
else:
    _BASE_DIR = Path("/home/pi/rodrigo_radio")

DEFAULT_HISTORY_FILE = _BASE_DIR / "data" / "history.json"
MAX_HISTORY_ENTRIES = 1000  # Keep last 1000 entries


class PlaybackHistory:
    """Manages playback history logging."""
    
    def __init__(self, history_file: Path = None):
        self.history_file = history_file or DEFAULT_HISTORY_FILE
        self._history: List[Dict] = []
        self._load_history()
    
    def _load_history(self):
        """Load history from JSON file."""
        try:
            if not self.history_file.exists():
                self._history = []
                return
            
            with open(self.history_file, 'r') as f:
                self._history = json.load(f)
            
            if not isinstance(self._history, list):
                self._history = []
            
            # Trim to max entries
            if len(self._history) > MAX_HISTORY_ENTRIES:
                self._history = self._history[-MAX_HISTORY_ENTRIES:]
                self._save_history()
            
            logger.debug(f"Loaded {len(self._history)} history entries")
            
        except Exception as e:
            logger.error(f"Error loading history: {e}")
            self._history = []
    
    def _save_history(self):
        """Save history to JSON file."""
        try:
            # Ensure directory exists
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.history_file, 'w') as f:
                json.dump(self._history, f, indent=2)
            
        except Exception as e:
            logger.error(f"Error saving history: {e}")
    
    def log_playback_start(self, source: Dict, item_name: Optional[str] = None):
        """
        Log the start of playback.
        
        Args:
            source: Source dictionary (from sources.json)
            item_name: Optional name of the current track/item
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': 'play',
            'source_id': source.get('id'),
            'source_label': source.get('label'),
            'source_type': source.get('type'),
            'item_name': item_name
        }
        
        self._history.append(entry)
        
        # Trim if needed
        if len(self._history) > MAX_HISTORY_ENTRIES:
            self._history = self._history[-MAX_HISTORY_ENTRIES:]
        
        self._save_history()
        logger.debug(f"Logged playback start: {source.get('label')}")
    
    def log_source_change(self, source: Dict):
        """Log a source change."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': 'source_change',
            'source_id': source.get('id'),
            'source_label': source.get('label'),
            'source_type': source.get('type')
        }
        
        self._history.append(entry)
        
        if len(self._history) > MAX_HISTORY_ENTRIES:
            self._history = self._history[-MAX_HISTORY_ENTRIES:]
        
        self._save_history()
        logger.debug(f"Logged source change: {source.get('label')}")
    
    def log_action(self, action: str, **kwargs):
        """
        Log a custom action.
        
        Args:
            action: Action name (e.g., 'pause', 'resume', 'next', 'previous')
            **kwargs: Additional data to log
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            **kwargs
        }
        
        self._history.append(entry)
        
        if len(self._history) > MAX_HISTORY_ENTRIES:
            self._history = self._history[-MAX_HISTORY_ENTRIES:]
        
        self._save_history()
    
    def get_recent(self, limit: int = 50) -> List[Dict]:
        """
        Get recent history entries.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of history entries, most recent first
        """
        return list(reversed(self._history[-limit:]))
    
    def get_all(self) -> List[Dict]:
        """Get all history entries (most recent first)."""
        return list(reversed(self._history))

