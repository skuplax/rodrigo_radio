"""Stats panel widget for Rodrigo Radio TUI Monitor."""

from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.reactive import reactive

from tui.services.stats_calculator import StatsCalculator


class StatsPanelWidget(Static):
    """Widget displaying today's statistics summary."""

    DEFAULT_CSS = """
    StatsPanelWidget {
        height: auto;
        min-height: 6;
        padding: 1;
        border: solid $primary-lighten-1;
        background: $surface-darken-1;
    }
    
    StatsPanelWidget .widget-title {
        text-style: bold;
        color: $primary-lighten-1;
        margin-bottom: 1;
    }
    
    StatsPanelWidget .stat-row {
        margin: 0;
    }
    
    StatsPanelWidget .stat-value {
        text-style: bold;
        color: $secondary;
    }
    
    StatsPanelWidget .stat-label {
        color: $text-muted;
    }
    """

    listening_time = reactive(0)
    tracks_played = reactive(0)
    interactions = reactive(0)
    sources_used = reactive(0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats_calc = StatsCalculator()

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Label("📊 TODAY'S STATS", classes="widget-title")
        yield Static("", id="stats-display")

    def on_mount(self) -> None:
        """Initialize widget on mount."""
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh statistics data."""
        try:
            stats = self.stats_calc.get_all_stats("today")
            self.listening_time = stats.get("listening_time_seconds", 0)
            self.tracks_played = stats.get("tracks_played", 0)
            self.interactions = stats.get("interactions", 0)
            self.sources_used = stats.get("sources_used", 0)
        except Exception:
            self.listening_time = 0
            self.tracks_played = 0
            self.interactions = 0
            self.sources_used = 0
        
        self._update_display()

    def _format_duration(self, seconds: int) -> str:
        """Format seconds to readable duration."""
        if seconds <= 0:
            return "0m"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def _update_display(self) -> None:
        """Update the display."""
        try:
            display = self.query_one("#stats-display", Static)
            
            lines = [
                f"⏱ Listening: {self._format_duration(self.listening_time)}",
                f"🎵 Tracks: {self.tracks_played}",
                f"🎛 Interactions: {self.interactions}",
                f"📻 Sources: {self.sources_used}",
            ]
            
            display.update("\n".join(lines))
        except Exception:
            pass

    def watch_listening_time(self, value: int) -> None:
        """React to listening time changes."""
        self._update_display()

    def watch_tracks_played(self, value: int) -> None:
        """React to tracks played changes."""
        self._update_display()


