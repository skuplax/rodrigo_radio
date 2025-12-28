"""Supabase client service for TUI Monitor.

Handles fetching events from Supabase for display in the TUI.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any
from pathlib import Path
import time

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL_SECONDS = 30  # How long to cache results
MAX_CACHE_SIZE = 1000   # Maximum events to cache


class SupabaseClient:
    """Client for fetching events from Supabase."""

    def __init__(self):
        """Initialize the Supabase client."""
        self._client: Optional[Client] = None
        self._is_connected = False
        self._last_error: Optional[str] = None
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}
        
        if not SUPABASE_AVAILABLE:
            self._last_error = "Supabase library not installed"
            return
        
        self._load_env()
        self._init_client()

    def _load_env(self) -> None:
        """Load environment variables."""
        # Try to load .env from project root
        project_root = Path(__file__).parent.parent.parent
        env_file = project_root / ".env"
        
        if DOTENV_AVAILABLE and env_file.exists():
            try:
                load_dotenv(env_file)
            except Exception as e:
                logger.debug(f"Error loading .env: {e}")
        
        # Get Supabase credentials
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
        
        # Try DATABASE_URL format if direct vars not set
        if not self.supabase_url:
            database_url = os.getenv("DATABASE_URL")
            if database_url and "supabase.co" in database_url:
                try:
                    if database_url.startswith("https://"):
                        self.supabase_url = database_url.rstrip("/")
                    else:
                        # Parse postgresql connection string
                        parts = database_url.split("@")
                        if len(parts) > 1:
                            host_part = parts[1].split(":")[0]
                            if host_part.startswith("db."):
                                project_ref = host_part.replace("db.", "").replace(".supabase.co", "")
                                self.supabase_url = f"https://{project_ref}.supabase.co"
                except Exception:
                    pass

    def _init_client(self) -> None:
        """Initialize the Supabase client."""
        if not self.supabase_url or not self.supabase_key:
            self._last_error = "Missing Supabase credentials"
            return
        
        try:
            self._client = create_client(self.supabase_url, self.supabase_key)
            self._is_connected = True
            self._last_error = None
        except Exception as e:
            self._last_error = str(e)
            self._is_connected = False

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._is_connected and self._client is not None

    @property
    def last_error(self) -> Optional[str]:
        """Get the last error message."""
        return self._last_error

    def _get_cached(self, cache_key: str) -> Optional[Any]:
        """Get cached value if still valid."""
        if cache_key not in self._cache:
            return None
        
        timestamp = self._cache_timestamps.get(cache_key, 0)
        if time.time() - timestamp > CACHE_TTL_SECONDS:
            # Cache expired
            del self._cache[cache_key]
            del self._cache_timestamps[cache_key]
            return None
        
        return self._cache[cache_key]

    def _set_cached(self, cache_key: str, value: Any) -> None:
        """Set a cached value."""
        self._cache[cache_key] = value
        self._cache_timestamps[cache_key] = time.time()

    def get_recent_events(self, limit: int = 50) -> List[Dict]:
        """
        Fetch recent events from Supabase.
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List of event dictionaries, most recent first
        """
        cache_key = f"recent_events_{limit}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        if not self.is_connected:
            return []
        
        try:
            response = self._client.table("event_logs") \
                .select("*") \
                .order("timestamp", desc=True) \
                .limit(limit) \
                .execute()
            
            events = self._process_events(response.data)
            self._set_cached(cache_key, events)
            self._is_connected = True
            self._last_error = None
            return events
            
        except Exception as e:
            self._last_error = str(e)
            self._is_connected = False
            return []

    def get_events_since(self, since_timestamp: str) -> List[Dict]:
        """
        Fetch events since a given timestamp.
        
        Args:
            since_timestamp: ISO format timestamp
            
        Returns:
            List of new events since the timestamp
        """
        if not self.is_connected:
            return []
        
        try:
            response = self._client.table("event_logs") \
                .select("*") \
                .gt("timestamp", since_timestamp) \
                .order("timestamp", desc=True) \
                .limit(100) \
                .execute()
            
            events = self._process_events(response.data)
            self._is_connected = True
            self._last_error = None
            return events
            
        except Exception as e:
            self._last_error = str(e)
            self._is_connected = False
            return []

    def get_events_by_type(self, event_type: str, limit: int = 50) -> List[Dict]:
        """
        Fetch events filtered by type.
        
        Args:
            event_type: Event type to filter by (user_input, system, audio, etc.)
            limit: Maximum number of events
            
        Returns:
            List of filtered events
        """
        cache_key = f"events_by_type_{event_type}_{limit}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        if not self.is_connected:
            return []
        
        try:
            response = self._client.table("event_logs") \
                .select("*") \
                .eq("event_type", event_type) \
                .order("timestamp", desc=True) \
                .limit(limit) \
                .execute()
            
            events = self._process_events(response.data)
            self._set_cached(cache_key, events)
            self._is_connected = True
            self._last_error = None
            return events
            
        except Exception as e:
            self._last_error = str(e)
            self._is_connected = False
            return []

    def get_events_in_range(self, start: datetime, end: datetime, limit: int = 500) -> List[Dict]:
        """
        Fetch events within a date range.
        
        Args:
            start: Start datetime
            end: End datetime
            limit: Maximum number of events
            
        Returns:
            List of events in the date range
        """
        if not self.is_connected:
            return []
        
        try:
            start_iso = start.isoformat()
            end_iso = end.isoformat()
            
            response = self._client.table("event_logs") \
                .select("*") \
                .gte("timestamp", start_iso) \
                .lte("timestamp", end_iso) \
                .order("timestamp", desc=True) \
                .limit(limit) \
                .execute()
            
            events = self._process_events(response.data)
            self._is_connected = True
            self._last_error = None
            return events
            
        except Exception as e:
            self._last_error = str(e)
            self._is_connected = False
            return []

    def get_today_events(self, limit: int = 500) -> List[Dict]:
        """
        Fetch all events from today.
        
        Args:
            limit: Maximum number of events
            
        Returns:
            List of today's events
        """
        cache_key = f"today_events_{limit}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        # Calculate today's start (midnight)
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        events = self.get_events_in_range(today_start, now, limit)
        self._set_cached(cache_key, events)
        return events

    def get_this_week_events(self, limit: int = 1000) -> List[Dict]:
        """
        Fetch events from this week.
        
        Args:
            limit: Maximum number of events
            
        Returns:
            List of this week's events
        """
        cache_key = f"week_events_{limit}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        
        events = self.get_events_in_range(week_start, now, limit)
        self._set_cached(cache_key, events)
        return events

    def get_latest_playback_event(self) -> Optional[Dict]:
        """
        Get the most recent playback event.
        
        Returns:
            The latest playback_start event or None
        """
        cache_key = "latest_playback"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        if not self.is_connected:
            return None
        
        try:
            response = self._client.table("event_logs") \
                .select("*") \
                .eq("action", "playback_start") \
                .order("timestamp", desc=True) \
                .limit(1) \
                .execute()
            
            if response.data:
                event = self._process_events(response.data)[0]
                self._set_cached(cache_key, event)
                return event
            return None
            
        except Exception as e:
            self._last_error = str(e)
            return None

    def get_latest_source_change(self) -> Optional[Dict]:
        """
        Get the most recent source change event.
        
        Returns:
            The latest source_change event or None
        """
        if not self.is_connected:
            return None
        
        try:
            response = self._client.table("event_logs") \
                .select("*") \
                .eq("action", "source_change") \
                .order("timestamp", desc=True) \
                .limit(1) \
                .execute()
            
            if response.data:
                return self._process_events(response.data)[0]
            return None
            
        except Exception as e:
            self._last_error = str(e)
            return None

    def _process_events(self, raw_events: List[Dict]) -> List[Dict]:
        """
        Process raw events from Supabase.
        
        Args:
            raw_events: Raw event data from Supabase
            
        Returns:
            Processed event list
        """
        processed = []
        for event in raw_events:
            processed.append({
                "timestamp": event.get("timestamp_local") or event.get("timestamp", ""),
                "timestamp_utc": event.get("timestamp", ""),
                "log_level": event.get("log_level", "INFO"),
                "event_type": event.get("event_type", ""),
                "action": event.get("action", ""),
                "source_id": event.get("source_id"),
                "source_label": event.get("source_label"),
                "source_type": event.get("source_type"),
                "item_name": event.get("item_name"),
                "status": event.get("status"),
                "duration_ms": event.get("duration_ms"),
                "value": event.get("value"),
                "message": event.get("message"),
                "error_message": event.get("error_message"),
                "attempt": event.get("attempt"),
            })
        return processed

    def test_connection(self) -> bool:
        """
        Test the Supabase connection.
        
        Returns:
            True if connection is working
        """
        if not self._client:
            return False
        
        try:
            response = self._client.table("event_logs") \
                .select("timestamp") \
                .limit(1) \
                .execute()
            self._is_connected = True
            self._last_error = None
            return True
        except Exception as e:
            self._is_connected = False
            self._last_error = str(e)
            return False

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self._cache_timestamps.clear()


