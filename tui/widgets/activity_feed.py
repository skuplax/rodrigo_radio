"""Activity feed widget for Rodrigo Radio TUI Monitor."""

from datetime import datetime
from typing import List, Dict, Optional

from textual.app import ComposeResult
from textual.widgets import Static, Label, RichLog
from textual.reactive import reactive

from tui.services.supabase_client import SupabaseClient
from tui.config import get_config, get_event_icon, get_event_color


class ActivityFeedWidget(Static):
    """Widget displaying real-time activity feed."""

    DEFAULT_CSS = """
    ActivityFeedWidget {
        height: 100%;
        padding: 1;
        border: solid $primary;
        background: $surface-darken-1;
    }
    
    ActivityFeedWidget .widget-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    
    ActivityFeedWidget RichLog {
        height: 1fr;
        background: $surface-darken-2;
        scrollbar-gutter: stable;
    }
    
    ActivityFeedWidget .connection-status {
        dock: top;
        height: 1;
        text-align: right;
        color: $text-muted;
    }
    
    ActivityFeedWidget .connected {
        color: $success;
    }
    
    ActivityFeedWidget .disconnected {
        color: $error;
    }
    """

    events: reactive[List[Dict]] = reactive([])
    is_connected = reactive(False)
    last_timestamp: reactive[Optional[str]] = reactive(None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.supabase = SupabaseClient()
        self._max_events = get_config().max_feed_events

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Label("📜 ACTIVITY FEED", classes="widget-title")
        yield Static("", id="connection-status", classes="connection-status")
        yield RichLog(id="activity-log", highlight=True, markup=True)

    def on_mount(self) -> None:
        """Initialize widget on mount."""
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh activity feed data."""
        self.is_connected = self.supabase.is_connected
        
        if self.last_timestamp:
            # Fetch only new events
            new_events = self.supabase.get_events_since(self.last_timestamp)
            if new_events:
                # Prepend new events (they come in desc order)
                self.events = new_events + self.events
                # Trim to max size
                if len(self.events) > self._max_events:
                    self.events = self.events[:self._max_events]
                # Update last timestamp
                self.last_timestamp = self.events[0].get("timestamp")
                # Add new events to log
                self._add_events_to_log(new_events)
        else:
            # Initial load
            self.events = self.supabase.get_recent_events(limit=50)
            if self.events:
                self.last_timestamp = self.events[0].get("timestamp")
            self._populate_log()
        
        self._update_connection_status()

    def _populate_log(self) -> None:
        """Populate the log with all events."""
        try:
            log = self.query_one("#activity-log", RichLog)
            log.clear()
            
            # Events are in desc order, reverse for chronological display
            for event in reversed(self.events):
                self._write_event(log, event)
                
        except Exception:
            pass

    def _add_events_to_log(self, new_events: List[Dict]) -> None:
        """Add new events to the log."""
        try:
            log = self.query_one("#activity-log", RichLog)
            
            # New events are in desc order, reverse for chronological
            for event in reversed(new_events):
                self._write_event(log, event)
                
        except Exception:
            pass

    def _write_event(self, log: RichLog, event: Dict) -> None:
        """Write a single event to the log."""
        timestamp = self._format_timestamp(event.get("timestamp", ""))
        action = event.get("action", "unknown")
        event_type = event.get("event_type", "")
        status = event.get("status", "")
        
        # Get icon and color
        icon = get_event_icon(action, event_type)
        color = get_event_color(action, event_type, status)
        
        # Build event text
        text_parts = [f"[dim]{timestamp}[/dim]", icon]
        
        # Format based on action type
        if action == "playback_start":
            item_name = event.get("item_name", "Unknown track")
            source = event.get("source_label", "")
            if source:
                text_parts.append(f"[{color}]{item_name}[/{color}] on {source}")
            else:
                text_parts.append(f"[{color}]{item_name}[/{color}]")
                
        elif action == "source_change":
            source = event.get("source_label", "Unknown")
            text_parts.append(f"[{color}]Switched to {source}[/{color}]")
            
        elif action.startswith("button_"):
            action_name = action.replace("button_", "").replace("_", " ").title()
            text_parts.append(f"[{color}]{action_name}[/{color}]")
            
        elif action == "encoder_switch_press":
            text_parts.append(f"[{color}]Mute Toggle[/{color}]")
            
        elif action in ("volume_set", "volume_adjust"):
            value = event.get("value")
            if value is not None:
                text_parts.append(f"[{color}]Volume: {value:.0f}%[/{color}]")
            else:
                text_parts.append(f"[{color}]Volume changed[/{color}]")
                
        elif action in ("startup", "shutdown"):
            text_parts.append(f"[{color}]System {action.title()}[/{color}]")
            
        elif action == "connection_failure":
            error = event.get("error_message", "Connection failed")
            text_parts.append(f"[{color}]Error: {error[:40]}[/{color}]")
            
        elif action == "retry_attempt":
            attempt = event.get("attempt", "?")
            text_parts.append(f"[{color}]Retry attempt {attempt}[/{color}]")
            
        else:
            # Generic format
            action_display = action.replace("_", " ").title()
            text_parts.append(f"[{color}]{action_display}[/{color}]")
        
        # Write to log
        log.write(" ".join(text_parts))

    def _format_timestamp(self, iso_string: str) -> str:
        """Format ISO timestamp to HH:MM:SS."""
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            return dt.strftime("%H:%M:%S")
        except Exception:
            return iso_string[:8] if len(iso_string) >= 8 else "??:??:??"

    def _update_connection_status(self) -> None:
        """Update the connection status display."""
        try:
            status = self.query_one("#connection-status", Static)
            config = get_config()
            icons = config.status_icons
            
            if self.is_connected:
                status.update(f"{icons.connected} Connected")
                status.remove_class("disconnected")
                status.add_class("connected")
            else:
                error = self.supabase.last_error or "Disconnected"
                status.update(f"{icons.disconnected} {error[:20]}")
                status.remove_class("connected")
                status.add_class("disconnected")
                
        except Exception:
            pass

    def watch_is_connected(self, value: bool) -> None:
        """React to connection status changes."""
        self._update_connection_status()

    def watch_events(self, value: List[Dict]) -> None:
        """React to events changes."""
        # Events are managed via _add_events_to_log, not full repopulate
        pass


