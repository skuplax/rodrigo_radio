"""Health panel widget for Rodrigo Radio TUI Monitor."""

from datetime import datetime
from typing import Optional

from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.reactive import reactive

from tui.services.supabase_client import SupabaseClient
from tui.services.player_status import PlayerStatusService
from tui.config import get_config


class HealthPanelWidget(Static):
    """Widget displaying system health status."""

    DEFAULT_CSS = """
    HealthPanelWidget {
        height: auto;
        min-height: 4;
        padding: 1;
        border: solid $primary;
        background: $surface-darken-1;
    }
    
    HealthPanelWidget .widget-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    
    HealthPanelWidget .health-good {
        color: $success;
    }
    
    HealthPanelWidget .health-warning {
        color: $warning;
    }
    
    HealthPanelWidget .health-error {
        color: $error;
    }
    """

    supabase_connected = reactive(False)
    rodrigo_running = reactive(False)
    raspotify_running = reactive(False)
    last_event_time: reactive[Optional[str]] = reactive(None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.supabase = SupabaseClient()
        self.player_status = PlayerStatusService()

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Label("🏥 SYSTEM HEALTH", classes="widget-title")
        yield Static("", id="health-display")

    def on_mount(self) -> None:
        """Initialize widget on mount."""
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh health data."""
        # Check Supabase connection
        self.supabase_connected = self.supabase.test_connection()
        
        # Check services
        services = self.player_status.get_service_status()
        self.rodrigo_running = services.get("rodrigo_radio", False)
        self.raspotify_running = services.get("raspotify", False)
        
        # Get last event time
        recent = self.supabase.get_recent_events(limit=1)
        if recent:
            self.last_event_time = recent[0].get("timestamp")
        else:
            self.last_event_time = None
        
        self._update_display()

    def _format_last_event(self) -> str:
        """Format last event time as relative time."""
        if not self.last_event_time:
            return "No events"
        
        try:
            event_time = datetime.fromisoformat(
                self.last_event_time.replace("Z", "+00:00")
            )
            now = datetime.now(event_time.tzinfo)
            diff = now - event_time
            
            seconds = int(diff.total_seconds())
            
            if seconds < 60:
                return f"{seconds}s ago"
            elif seconds < 3600:
                return f"{seconds // 60}m ago"
            elif seconds < 86400:
                return f"{seconds // 3600}h ago"
            else:
                return f"{seconds // 86400}d ago"
        except Exception:
            return "Unknown"

    def _update_display(self) -> None:
        """Update the display."""
        config = get_config()
        icons = config.status_icons
        
        try:
            display = self.query_one("#health-display", Static)
            
            lines = []
            
            # Supabase status
            if self.supabase_connected:
                lines.append(f"[green]{icons.service_running}[/green] Supabase: Connected")
            else:
                error = self.supabase.last_error or "Disconnected"
                lines.append(f"[red]{icons.service_stopped}[/red] Supabase: {error[:30]}")
            
            # Service status (only shown if running locally)
            if self.rodrigo_running or self.raspotify_running:
                if self.rodrigo_running:
                    lines.append(f"[green]{icons.service_running}[/green] rodrigo_radio: Running")
                else:
                    lines.append(f"[red]{icons.service_stopped}[/red] rodrigo_radio: Stopped")
                
                if self.raspotify_running:
                    lines.append(f"[green]{icons.service_running}[/green] raspotify: Running")
                else:
                    lines.append(f"[yellow]{icons.service_stopped}[/yellow] raspotify: Stopped")
            
            # Last event
            last_event_str = self._format_last_event()
            lines.append(f"📡 Last event: {last_event_str}")
            
            display.update("\n".join(lines))
            
        except Exception:
            pass

    def watch_supabase_connected(self, value: bool) -> None:
        """React to connection status changes."""
        self._update_display()

    def watch_rodrigo_running(self, value: bool) -> None:
        """React to service status changes."""
        self._update_display()

    def watch_last_event_time(self, value: Optional[str]) -> None:
        """React to last event time changes."""
        self._update_display()


