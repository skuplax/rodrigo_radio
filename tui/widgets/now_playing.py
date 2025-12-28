"""Now Playing widget for Rodrigo Radio TUI Monitor."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, Label, ProgressBar
from textual.reactive import reactive

from tui.services.supabase_client import SupabaseClient
from tui.services.player_status import PlayerStatusService
from tui.config import get_config, get_source_icon


class NowPlayingWidget(Static):
    """Widget displaying current playback status."""

    DEFAULT_CSS = """
    NowPlayingWidget {
        height: auto;
        min-height: 10;
        padding: 1;
        border: solid $success;
        background: $surface-darken-1;
    }
    
    NowPlayingWidget .widget-title {
        text-style: bold;
        color: $success;
        margin-bottom: 1;
    }
    
    NowPlayingWidget .source-info {
        color: $success;
        text-style: bold;
    }
    
    NowPlayingWidget .track-info {
        color: $text;
        margin-top: 1;
    }
    
    NowPlayingWidget .artist-info {
        color: $text-muted;
    }
    
    NowPlayingWidget .status-playing {
        color: $success;
    }
    
    NowPlayingWidget .status-paused {
        color: $warning;
    }
    
    NowPlayingWidget .status-stopped {
        color: $error;
    }
    
    NowPlayingWidget .no-data {
        color: $text-muted;
        text-style: italic;
    }
    """

    source_name = reactive("")
    source_type = reactive("")
    track_name = reactive("")
    artist_name = reactive("")
    status = reactive("stopped")
    progress = reactive(0.0)
    position = reactive("")
    duration = reactive("")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.supabase = SupabaseClient()
        self.player_status = PlayerStatusService()

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Label("🎵 NOW PLAYING", classes="widget-title")
        yield Static("", id="source-display", classes="source-info")
        yield Static("", id="track-display", classes="track-info")
        yield Static("", id="artist-display", classes="artist-info")
        yield Static("", id="status-display")
        yield ProgressBar(id="progress-bar", total=100, show_eta=False)
        yield Static("", id="position-display")

    def on_mount(self) -> None:
        """Initialize widget on mount."""
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh the widget data from sources."""
        # Get current source from local state
        current_source = self.player_status.get_current_source()
        
        if current_source:
            source_icon = get_source_icon(current_source.get("type", ""))
            self.source_name = current_source.get("label", "Unknown")
            self.source_type = current_source.get("type", "")
        else:
            self.source_name = "No source"
            self.source_type = ""
        
        # Get latest playback event from Supabase
        latest = self.supabase.get_latest_playback_event()
        
        if latest:
            self.track_name = latest.get("item_name") or ""
            self.artist_name = ""  # Parse from track name if available
            
            # Try to extract artist from "Artist - Track" format
            if self.track_name and " - " in self.track_name:
                parts = self.track_name.split(" - ", 1)
                self.artist_name = parts[0]
                self.track_name = parts[1] if len(parts) > 1 else self.track_name
            
            # Determine status based on recent events
            recent_events = self.supabase.get_recent_events(limit=5)
            self.status = self._determine_status(recent_events)
        else:
            self.track_name = ""
            self.artist_name = ""
            self.status = "stopped"
        
        # Update display
        self._update_display()

    def _determine_status(self, recent_events: list) -> str:
        """Determine playback status from recent events."""
        for event in recent_events:
            action = event.get("action", "")
            if action == "playback_start":
                return "playing"
            elif action in ("pause", "button_play_pause"):
                # Check if this was a pause or resume
                # For now, assume last action determines state
                return "paused"
            elif action == "shutdown":
                return "stopped"
        return "playing"  # Default to playing if we have playback events

    def _update_display(self) -> None:
        """Update the display elements."""
        config = get_config()
        
        # Source display
        try:
            source_display = self.query_one("#source-display", Static)
            if self.source_name:
                icon = get_source_icon(self.source_type)
                source_display.update(f"{icon} {self.source_name}")
            else:
                source_display.update("No source selected")
                source_display.add_class("no-data")
        except Exception:
            pass
        
        # Track display
        try:
            track_display = self.query_one("#track-display", Static)
            if self.track_name:
                track_display.update(f"🎶 {self.track_name}")
                track_display.remove_class("no-data")
            else:
                track_display.update("No track playing")
                track_display.add_class("no-data")
        except Exception:
            pass
        
        # Artist display
        try:
            artist_display = self.query_one("#artist-display", Static)
            if self.artist_name:
                artist_display.update(f"👤 {self.artist_name}")
                artist_display.remove_class("no-data")
            else:
                artist_display.update("")
        except Exception:
            pass
        
        # Status display
        try:
            status_display = self.query_one("#status-display", Static)
            icons = config.status_icons
            
            if self.status == "playing":
                status_display.update(f"{icons.playing} Playing")
                status_display.remove_class("status-paused", "status-stopped")
                status_display.add_class("status-playing")
            elif self.status == "paused":
                status_display.update(f"{icons.paused} Paused")
                status_display.remove_class("status-playing", "status-stopped")
                status_display.add_class("status-paused")
            else:
                status_display.update(f"{icons.stopped} Stopped")
                status_display.remove_class("status-playing", "status-paused")
                status_display.add_class("status-stopped")
        except Exception:
            pass
        
        # Progress bar (placeholder - would need live position data)
        try:
            progress_bar = self.query_one("#progress-bar", ProgressBar)
            # For now, just show indeterminate or hidden
            progress_bar.update(progress=0)
        except Exception:
            pass
        
        # Position display
        try:
            position_display = self.query_one("#position-display", Static)
            if self.position and self.duration:
                position_display.update(f"{self.position} / {self.duration}")
            else:
                position_display.update("")
        except Exception:
            pass

    def watch_source_name(self, value: str) -> None:
        """React to source name changes."""
        self._update_display()

    def watch_track_name(self, value: str) -> None:
        """React to track name changes."""
        self._update_display()

    def watch_status(self, value: str) -> None:
        """React to status changes."""
        self._update_display()


