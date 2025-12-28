"""Statistics calculator service for TUI Monitor.

Calculates various statistics from event data.
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from tui.services.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


class StatsCalculator:
    """Calculator for playback statistics."""

    def __init__(self, supabase_client: Optional[SupabaseClient] = None):
        """
        Initialize the stats calculator.
        
        Args:
            supabase_client: Supabase client instance
        """
        self.supabase = supabase_client or SupabaseClient()
        self._cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=1)

    def get_all_stats(self, period: str = "today") -> Dict[str, Any]:
        """
        Get all statistics for a period.
        
        Args:
            period: 'today', 'week', 'month', or 'all'
            
        Returns:
            Dictionary with all stats
        """
        events = self._get_events_for_period(period)
        
        return {
            "listening_time_seconds": self._calculate_listening_time(events),
            "tracks_played": self._count_tracks(events),
            "interactions": self._count_interactions(events),
            "sources_used": self._count_sources(events),
            "source_distribution": self._calculate_source_distribution(events),
            "activity_by_hour": self._calculate_activity_by_hour(events),
            "most_played_sources": self._get_most_played_sources(events),
            "event_counts": self._count_events_by_type(events),
        }

    def get_listening_time(self, period: str = "today") -> int:
        """
        Calculate total listening time in seconds.
        
        Args:
            period: Time period
            
        Returns:
            Listening time in seconds
        """
        events = self._get_events_for_period(period)
        return self._calculate_listening_time(events)

    def get_source_distribution(self, period: str = "today") -> Dict[str, float]:
        """
        Get distribution of listening time by source.
        
        Args:
            period: Time period
            
        Returns:
            Dictionary mapping source labels to percentages
        """
        events = self._get_events_for_period(period)
        return self._calculate_source_distribution(events)

    def get_track_count(self, period: str = "today") -> int:
        """
        Count unique tracks played.
        
        Args:
            period: Time period
            
        Returns:
            Number of tracks played
        """
        events = self._get_events_for_period(period)
        return self._count_tracks(events)

    def get_interaction_count(self, period: str = "today") -> int:
        """
        Count user interactions (button presses).
        
        Args:
            period: Time period
            
        Returns:
            Number of interactions
        """
        events = self._get_events_for_period(period)
        return self._count_interactions(events)

    def get_activity_by_hour(self, period: str = "today") -> Dict[int, int]:
        """
        Get activity counts by hour of day.
        
        Args:
            period: Time period
            
        Returns:
            Dictionary mapping hour (0-23) to event count
        """
        events = self._get_events_for_period(period)
        return self._calculate_activity_by_hour(events)

    def _get_events_for_period(self, period: str) -> List[Dict]:
        """Get events for the specified period."""
        cache_key = f"events_{period}"
        
        # Check cache
        if cache_key in self._cache:
            cache_time = self._cache_time.get(cache_key)
            if cache_time and datetime.now() - cache_time < self._cache_ttl:
                return self._cache[cache_key]
        
        # Fetch events
        if period == "today":
            events = self.supabase.get_today_events(limit=1000)
        elif period == "week":
            events = self.supabase.get_this_week_events(limit=2000)
        elif period == "month":
            now = datetime.now(timezone.utc)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            events = self.supabase.get_events_in_range(month_start, now, limit=5000)
        else:  # all
            events = self.supabase.get_recent_events(limit=5000)
        
        # Cache results
        self._cache[cache_key] = events
        self._cache_time[cache_key] = datetime.now()
        
        return events

    def _calculate_listening_time(self, events: List[Dict]) -> int:
        """
        Calculate total listening time from events.
        
        Estimates based on playback_start events and time between them.
        """
        playback_events = [
            e for e in events 
            if e.get("action") == "playback_start"
        ]
        
        if not playback_events:
            return 0
        
        # Sort by timestamp
        sorted_events = sorted(
            playback_events,
            key=lambda e: e.get("timestamp", ""),
        )
        
        total_seconds = 0
        
        for i in range(len(sorted_events) - 1):
            current = sorted_events[i]
            next_event = sorted_events[i + 1]
            
            try:
                current_time = datetime.fromisoformat(
                    current.get("timestamp", "").replace("Z", "+00:00")
                )
                next_time = datetime.fromisoformat(
                    next_event.get("timestamp", "").replace("Z", "+00:00")
                )
                
                # Calculate duration between events
                duration = (next_time - current_time).total_seconds()
                
                # Cap at 30 minutes per track (reasonable assumption)
                if 0 < duration < 30 * 60:
                    total_seconds += int(duration)
                    
            except Exception:
                continue
        
        # Add estimate for last track (assume 3 minutes average)
        if sorted_events:
            total_seconds += 3 * 60
        
        return total_seconds

    def _count_tracks(self, events: List[Dict]) -> int:
        """Count playback_start events."""
        return len([
            e for e in events 
            if e.get("action") == "playback_start"
        ])

    def _count_interactions(self, events: List[Dict]) -> int:
        """Count user input events."""
        return len([
            e for e in events 
            if e.get("event_type") == "user_input"
        ])

    def _count_sources(self, events: List[Dict]) -> int:
        """Count unique sources used."""
        sources = set()
        for event in events:
            source_id = event.get("source_id")
            if source_id:
                sources.add(source_id)
        return len(sources)

    def _calculate_source_distribution(self, events: List[Dict]) -> Dict[str, float]:
        """Calculate percentage of tracks per source."""
        source_counts: Dict[str, int] = defaultdict(int)
        
        for event in events:
            if event.get("action") == "playback_start":
                source_label = event.get("source_label") or event.get("source_id") or "Unknown"
                source_counts[source_label] += 1
        
        total = sum(source_counts.values())
        if total == 0:
            return {}
        
        return {
            source: (count / total) * 100
            for source, count in source_counts.items()
        }

    def _calculate_activity_by_hour(self, events: List[Dict]) -> Dict[int, int]:
        """Calculate event counts by hour of day."""
        hour_counts: Dict[int, int] = defaultdict(int)
        
        for event in events:
            timestamp = event.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                hour_counts[dt.hour] += 1
            except Exception:
                continue
        
        # Ensure all hours are represented
        return {hour: hour_counts.get(hour, 0) for hour in range(24)}

    def _get_most_played_sources(self, events: List[Dict], limit: int = 5) -> List[Dict]:
        """Get most played sources."""
        source_counts: Dict[str, Dict] = {}
        
        for event in events:
            if event.get("action") == "playback_start":
                source_id = event.get("source_id")
                if not source_id:
                    continue
                
                if source_id not in source_counts:
                    source_counts[source_id] = {
                        "source_id": source_id,
                        "source_label": event.get("source_label") or source_id,
                        "source_type": event.get("source_type"),
                        "count": 0,
                    }
                source_counts[source_id]["count"] += 1
        
        # Sort by count and return top N
        sorted_sources = sorted(
            source_counts.values(),
            key=lambda x: x["count"],
            reverse=True,
        )
        
        return sorted_sources[:limit]

    def _count_events_by_type(self, events: List[Dict]) -> Dict[str, int]:
        """Count events by event type."""
        type_counts: Dict[str, int] = defaultdict(int)
        
        for event in events:
            event_type = event.get("event_type") or "unknown"
            type_counts[event_type] += 1
        
        return dict(type_counts)

    def clear_cache(self) -> None:
        """Clear the stats cache."""
        self._cache.clear()
        self._cache_time.clear()


