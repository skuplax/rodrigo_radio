"""Source list widget for Rodrigo Radio TUI Monitor."""

from typing import List, Dict

from textual.app import ComposeResult
from textual.widgets import Static, Label, ListView, ListItem
from textual.reactive import reactive

from tui.services.player_status import PlayerStatusService
from tui.config import get_config, get_source_icon


class SourceListWidget(Static):
    """Widget displaying list of available sources."""

    DEFAULT_CSS = """
    SourceListWidget {
        height: auto;
        min-height: 8;
        max-height: 15;
        padding: 1;
        border: solid $secondary;
        background: $surface-darken-1;
    }
    
    SourceListWidget .widget-title {
        text-style: bold;
        color: $secondary;
        margin-bottom: 1;
    }
    
    SourceListWidget .source-item {
        padding: 0 1;
    }
    
    SourceListWidget .source-current {
        background: $primary;
        text-style: bold;
    }
    
    SourceListWidget .source-spotify {
        color: $success;
    }
    
    SourceListWidget .source-youtube {
        color: $error;
    }
    
    SourceListWidget .no-sources {
        color: $text-muted;
        text-style: italic;
    }
    """

    current_index = reactive(0)
    sources: reactive[List[Dict]] = reactive([])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player_status = PlayerStatusService()

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Label("📻 SOURCES", classes="widget-title")
        yield Static("", id="sources-list-display")

    def on_mount(self) -> None:
        """Initialize widget on mount."""
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh sources list."""
        self.sources = self.player_status.get_sources_list()
        self.current_index = self.player_status.get_current_source_index()
        self._update_display()

    def _update_display(self) -> None:
        """Update the sources display."""
        try:
            display = self.query_one("#sources-list-display", Static)
            
            if not self.sources:
                display.update("No sources configured")
                display.add_class("no-sources")
                return
            
            display.remove_class("no-sources")
            
            lines = []
            for i, source in enumerate(self.sources):
                label = source.get("label", source.get("id", "Unknown"))
                source_type = source.get("type", "")
                icon = get_source_icon(source_type)
                
                # Mark current source
                if i == self.current_index:
                    marker = "►"
                    lines.append(f"[bold]{marker} {icon} {label}[/bold]")
                else:
                    marker = " "
                    lines.append(f"{marker} {icon} {label}")
            
            display.update("\n".join(lines))
            
        except Exception:
            pass

    def watch_current_index(self, value: int) -> None:
        """React to current index changes."""
        self._update_display()

    def watch_sources(self, value: List[Dict]) -> None:
        """React to sources list changes."""
        self._update_display()


