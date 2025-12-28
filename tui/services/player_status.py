"""Local player status service for TUI Monitor.

Handles reading local state files and checking service status.
"""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Default paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_STATE_FILE = PROJECT_ROOT / "data" / "state.json"
DEFAULT_SOURCES_FILE = PROJECT_ROOT / "config" / "sources.json"


class PlayerStatusService:
    """Service for getting local player status information."""

    def __init__(
        self,
        state_file: Optional[Path] = None,
        sources_file: Optional[Path] = None,
    ):
        """
        Initialize the player status service.
        
        Args:
            state_file: Path to state.json file
            sources_file: Path to sources.json file
        """
        self.state_file = state_file or DEFAULT_STATE_FILE
        self.sources_file = sources_file or DEFAULT_SOURCES_FILE
        self._sources_cache: Optional[List[Dict]] = None
        self._sources_mtime: float = 0

    def get_current_source(self) -> Optional[Dict]:
        """
        Get the currently selected source.
        
        Returns:
            Source dictionary or None if not available
        """
        try:
            state = self._read_state()
            if not state:
                return None
            
            source_index = state.get("current_source_index", 0)
            sources = self.get_sources_list()
            
            if sources and 0 <= source_index < len(sources):
                return sources[source_index]
            
            return None
        except Exception as e:
            logger.error(f"Error getting current source: {e}")
            return None

    def get_current_source_index(self) -> int:
        """
        Get the current source index.
        
        Returns:
            Current source index or 0 if not available
        """
        try:
            state = self._read_state()
            return state.get("current_source_index", 0) if state else 0
        except Exception:
            return 0

    def get_sources_list(self) -> List[Dict]:
        """
        Get the list of configured sources.
        
        Returns:
            List of source dictionaries
        """
        try:
            # Check if cache is still valid (file hasn't changed)
            if self.sources_file.exists():
                mtime = self.sources_file.stat().st_mtime
                if self._sources_cache is not None and mtime == self._sources_mtime:
                    return self._sources_cache
            
            if not self.sources_file.exists():
                return []
            
            with open(self.sources_file, "r") as f:
                sources = json.load(f)
            
            self._sources_cache = sources
            self._sources_mtime = self.sources_file.stat().st_mtime
            return sources
            
        except Exception as e:
            logger.error(f"Error reading sources file: {e}")
            return []

    def get_state_info(self) -> Dict[str, Any]:
        """
        Get full state information.
        
        Returns:
            Dictionary with state info
        """
        state = self._read_state()
        if not state:
            return {
                "available": False,
                "current_source_index": 0,
                "last_updated": None,
            }
        
        return {
            "available": True,
            "current_source_index": state.get("current_source_index", 0),
            "last_updated": state.get("last_updated"),
        }

    def _read_state(self) -> Optional[Dict]:
        """Read the state file."""
        try:
            if not self.state_file.exists():
                return None
            
            with open(self.state_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading state file: {e}")
            return None

    def is_service_running(self, service_name: str = "rodrigo_radio") -> bool:
        """
        Check if a systemd service is running.
        
        Args:
            service_name: Name of the systemd service
            
        Returns:
            True if service is running
        """
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "--quiet", service_name],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        except Exception:
            return False

    def is_raspotify_running(self) -> bool:
        """
        Check if raspotify service is running.
        
        Returns:
            True if raspotify is running
        """
        # Try systemctl first
        if self.is_service_running("raspotify"):
            return True
        
        # Fallback: check for librespot process
        try:
            result = subprocess.run(
                ["pgrep", "-f", "librespot"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_service_status(self) -> Dict[str, Any]:
        """
        Get status of relevant services.
        
        Returns:
            Dictionary with service status
        """
        return {
            "rodrigo_radio": self.is_service_running("rodrigo_radio"),
            "raspotify": self.is_raspotify_running(),
        }

    def get_volume_info(self) -> Optional[Dict[str, Any]]:
        """
        Get current volume information from ALSA.
        
        Returns:
            Dictionary with volume info or None
        """
        try:
            result = subprocess.run(
                ["amixer", "get", "PCM"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode != 0:
                return None
            
            output = result.stdout
            
            # Parse volume percentage
            import re
            percent_match = re.search(r"\[(\d+)%\]", output)
            db_match = re.search(r"\[(-?\d+\.?\d*)dB\]", output)
            mute_match = re.search(r"\[(on|off)\]", output)
            
            return {
                "percentage": int(percent_match.group(1)) if percent_match else None,
                "db": float(db_match.group(1)) if db_match else None,
                "muted": mute_match.group(1) == "off" if mute_match else False,
            }
            
        except Exception as e:
            logger.error(f"Error getting volume info: {e}")
            return None

    def get_time_volume_mode(self) -> str:
        """
        Get the current time-based volume mode.
        
        Returns:
            'day', 'evening', or 'night' based on current time
        """
        from datetime import time as dt_time
        now = datetime.now().time()
        
        # Night: 7pm (19:00) to 7am (07:00)
        if dt_time(19, 0) <= now or now < dt_time(7, 0):
            return "night"
        
        # Morning transition: 7am-8am stays at night
        if dt_time(7, 0) <= now < dt_time(8, 0):
            return "night"
        
        # Morning transition: 8am-9am is evening
        if dt_time(8, 0) <= now < dt_time(9, 0):
            return "evening"
        
        # Evening transition: 5pm-6pm is still day
        if dt_time(17, 0) <= now < dt_time(18, 0):
            return "day"
        
        # Evening transition: 6pm-7pm
        if dt_time(18, 0) <= now < dt_time(19, 0):
            return "evening"
        
        # Day: 9am-5pm
        return "day"

    def get_playback_status(self) -> Dict[str, Any]:
        """
        Get comprehensive playback status.
        
        Returns:
            Dictionary with playback status
        """
        current_source = self.get_current_source()
        sources = self.get_sources_list()
        state_info = self.get_state_info()
        volume_info = self.get_volume_info()
        services = self.get_service_status()
        
        return {
            "current_source": current_source,
            "current_index": state_info.get("current_source_index", 0),
            "total_sources": len(sources),
            "sources": sources,
            "state_available": state_info.get("available", False),
            "last_updated": state_info.get("last_updated"),
            "volume": volume_info,
            "time_mode": self.get_time_volume_mode(),
            "services": services,
        }

    def set_source(self, source_identifier) -> bool:
        """
        Set the current source by index, ID, or label.
        
        Args:
            source_identifier: Index (int), source ID (str), or label (str)
            
        Returns:
            True if source was changed successfully
        """
        sources = self.get_sources_list()
        if not sources:
            return False
        
        target_index = None
        
        # Try as integer index
        if isinstance(source_identifier, int):
            if 0 <= source_identifier < len(sources):
                target_index = source_identifier
        else:
            # Try as source ID or label
            source_id_lower = str(source_identifier).lower()
            for i, source in enumerate(sources):
                if source.get("id", "").lower() == source_id_lower:
                    target_index = i
                    break
                if source.get("label", "").lower() == source_id_lower:
                    target_index = i
                    break
                # Partial match on label
                if source_id_lower in source.get("label", "").lower():
                    target_index = i
                    break
        
        if target_index is None:
            return False
        
        # Update state file
        try:
            state = self._read_state() or {}
            state["current_source_index"] = target_index
            state["last_updated"] = datetime.now().isoformat()
            
            # Ensure data directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
            
            return True
            
        except Exception as e:
            logger.error(f"Error setting source: {e}")
            return False


