"""Statistics screen for Rodrigo Radio TUI Monitor."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Label, Select, ProgressBar
from textual.binding import Binding

from tui.services.stats_calculator import StatsCalculator


class StatsScreen(Screen):
    """Statistics and analytics screen."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.stats_calc = StatsCalculator()
        self.current_period = "today"

    def compose(self) -> ComposeResult:
        """Compose the statistics screen layout."""
        yield Header()
        
        with Container(id="stats-container"):
            # Period selector
            with Horizontal(id="stats-header"):
                yield Label("Period: ", classes="stats-label")
                yield Select(
                    options=[
                        ("Today", "today"),
                        ("This Week", "week"),
                        ("This Month", "month"),
                        ("All Time", "all"),
                    ],
                    id="period-selector",
                    value="today",
                )
            
            # Stats grid
            with Grid(id="stats-grid"):
                # Listening time
                with Vertical(classes="stat-box"):
                    yield Label("⏱ Listening Time", classes="stat-title")
                    yield Static("--:--:--", id="stat-listening-time", classes="stat-value-large")
                
                # Tracks played
                with Vertical(classes="stat-box"):
                    yield Label("🎵 Tracks Played", classes="stat-title")
                    yield Static("--", id="stat-tracks", classes="stat-value-large")
                
                # User interactions
                with Vertical(classes="stat-box"):
                    yield Label("🎛 Interactions", classes="stat-title")
                    yield Static("--", id="stat-interactions", classes="stat-value-large")
                
                # Sources used
                with Vertical(classes="stat-box"):
                    yield Label("📻 Sources Used", classes="stat-title")
                    yield Static("--", id="stat-sources", classes="stat-value-large")
            
            # Source distribution
            with Vertical(id="source-distribution"):
                yield Label("📊 Source Distribution", classes="section-title")
                yield Static("Loading...", id="source-dist-content")
            
            # Activity by hour (heatmap)
            with Vertical(id="activity-heatmap"):
                yield Label("📈 Activity by Hour", classes="section-title")
                yield Static("Loading...", id="activity-heatmap-content")
        
        yield Footer()

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh statistics data."""
        try:
            stats = self.stats_calc.get_all_stats(self.current_period)
            self._update_display(stats)
        except Exception as e:
            self.notify(f"Error loading stats: {e}", severity="error", timeout=5)

    def _update_display(self, stats: Dict) -> None:
        """Update the display with stats data."""
        # Update main stats
        try:
            listening_time = self.query_one("#stat-listening-time", Static)
            listening_time.update(self._format_duration(stats.get("listening_time_seconds", 0)))
        except Exception:
            pass
        
        try:
            tracks = self.query_one("#stat-tracks", Static)
            tracks.update(str(stats.get("tracks_played", 0)))
        except Exception:
            pass
        
        try:
            interactions = self.query_one("#stat-interactions", Static)
            interactions.update(str(stats.get("interactions", 0)))
        except Exception:
            pass
        
        try:
            sources = self.query_one("#stat-sources", Static)
            sources.update(str(stats.get("sources_used", 0)))
        except Exception:
            pass
        
        # Update source distribution
        try:
            source_dist = self.query_one("#source-dist-content", Static)
            dist_text = self._format_source_distribution(stats.get("source_distribution", {}))
            source_dist.update(dist_text)
        except Exception:
            pass
        
        # Update activity heatmap
        try:
            heatmap = self.query_one("#activity-heatmap-content", Static)
            heatmap_text = self._format_activity_heatmap(stats.get("activity_by_hour", {}))
            heatmap.update(heatmap_text)
        except Exception:
            pass

    def _format_duration(self, seconds: int) -> str:
        """Format seconds to HH:MM:SS."""
        if seconds <= 0:
            return "0:00:00"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"

    def _format_source_distribution(self, distribution: Dict[str, float]) -> str:
        """Format source distribution as text bars."""
        if not distribution:
            return "No data available"
        
        lines = []
        max_label_len = max(len(label) for label in distribution.keys()) if distribution else 10
        
        for source, percentage in sorted(distribution.items(), key=lambda x: -x[1]):
            bar_width = int(percentage / 100 * 30)
            bar = "█" * bar_width + "░" * (30 - bar_width)
            lines.append(f"{source:<{max_label_len}} [{bar}] {percentage:.1f}%")
        
        return "\n".join(lines) if lines else "No data"

    def _format_activity_heatmap(self, activity: Dict[int, int]) -> str:
        """Format hourly activity as a text heatmap."""
        if not activity:
            return "No data available"
        
        max_count = max(activity.values()) if activity else 1
        
        lines = []
        # Header
        lines.append("Hour:  " + " ".join(f"{h:2d}" for h in range(0, 24)))
        
        # Build heatmap row
        blocks = []
        for hour in range(24):
            count = activity.get(hour, 0)
            if max_count > 0:
                intensity = count / max_count
            else:
                intensity = 0
            
            # Map intensity to block character
            if intensity == 0:
                blocks.append("░░")
            elif intensity < 0.25:
                blocks.append("▒▒")
            elif intensity < 0.5:
                blocks.append("▓▓")
            elif intensity < 0.75:
                blocks.append("██")
            else:
                blocks.append("██")
        
        lines.append("Events:" + " ".join(blocks))
        
        return "\n".join(lines)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle period selection change."""
        if event.select.id == "period-selector":
            self.current_period = event.value
            self.refresh_data()

    def action_refresh(self) -> None:
        """Handle manual refresh action."""
        self.refresh_data()
        self.notify("Statistics refreshed", timeout=2)


