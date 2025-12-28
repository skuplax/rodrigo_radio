"""Dashboard screen for Rodrigo Radio TUI Monitor."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Label

from tui.widgets.now_playing import NowPlayingWidget
from tui.widgets.activity_feed import ActivityFeedWidget
from tui.widgets.source_list import SourceListWidget
from tui.widgets.volume_bar import VolumeBarWidget
from tui.widgets.stats_panel import StatsPanelWidget
from tui.widgets.health_panel import HealthPanelWidget


class DashboardScreen(Screen):
    """Main dashboard screen showing real-time status."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the dashboard layout."""
        yield Header()
        
        with Container(id="dashboard-container"):
            # Left panel: Now Playing, Sources, Volume
            with Vertical(id="left-panel"):
                yield NowPlayingWidget(id="now-playing")
                yield SourceListWidget(id="source-list")
                yield VolumeBarWidget(id="volume-bar")
                yield StatsPanelWidget(id="stats-panel")
                yield HealthPanelWidget(id="health-panel")
            
            # Right panel: Activity Feed
            with Vertical(id="right-panel"):
                yield ActivityFeedWidget(id="activity-feed")
        
        yield Footer()

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        self.refresh_data()
        # Set up periodic refresh
        self.set_interval(5.0, self.refresh_data)

    def refresh_data(self) -> None:
        """Refresh all widgets with latest data."""
        # Refresh each widget that has a refresh method
        for widget_id in ["now-playing", "activity-feed", "source-list", 
                          "volume-bar", "stats-panel", "health-panel"]:
            try:
                widget = self.query_one(f"#{widget_id}")
                if hasattr(widget, "refresh_data"):
                    widget.refresh_data()
            except Exception:
                pass  # Widget may not exist yet

    def action_refresh(self) -> None:
        """Handle manual refresh action."""
        self.refresh_data()
        self.notify("Dashboard refreshed", timeout=2)


