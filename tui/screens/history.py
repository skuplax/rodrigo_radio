"""History browser screen for Rodrigo Radio TUI Monitor."""

from datetime import datetime, timedelta
from typing import List, Dict, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, DataTable, Label, Input, Select, Static
from textual.binding import Binding

from tui.services.supabase_client import SupabaseClient


class HistoryScreen(Screen):
    """History browser screen with filtering and search."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "app.pop_screen", "Back"),
        Binding("f", "focus_filter", "Filter"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.supabase = SupabaseClient()
        self.events: List[Dict] = []
        self.current_filter: Optional[str] = None

    def compose(self) -> ComposeResult:
        """Compose the history screen layout."""
        yield Header()
        
        with Container(id="history-container"):
            # Filters row
            with Horizontal(id="history-filters"):
                yield Label("Filter by type: ")
                yield Select(
                    options=[
                        ("All Events", None),
                        ("Playback", "system"),
                        ("User Input", "user_input"),
                        ("Audio", "audio"),
                        ("Network", "network"),
                        ("Config", "config"),
                    ],
                    id="type-filter",
                    value=None,
                )
                yield Label(" | ", classes="separator")
                yield Input(placeholder="Search...", id="search-input")
            
            # History table
            yield DataTable(id="history-table")
        
        yield Footer()

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        # Set up the data table
        table = self.query_one("#history-table", DataTable)
        table.add_columns("Time", "Event", "Source", "Details")
        table.cursor_type = "row"
        
        # Load initial data
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh the history data."""
        try:
            self.events = self.supabase.get_recent_events(limit=200)
            self._update_table()
        except Exception as e:
            self.notify(f"Error loading history: {e}", severity="error", timeout=5)

    def _update_table(self) -> None:
        """Update the table with current events and filters."""
        table = self.query_one("#history-table", DataTable)
        table.clear()
        
        # Apply filter
        filtered_events = self.events
        if self.current_filter:
            filtered_events = [e for e in self.events 
                             if e.get("event_type") == self.current_filter]
        
        # Apply search (from input)
        try:
            search_input = self.query_one("#search-input", Input)
            search_text = search_input.value.lower() if search_input.value else ""
            if search_text:
                filtered_events = [
                    e for e in filtered_events
                    if search_text in str(e.get("action", "")).lower()
                    or search_text in str(e.get("source_label", "")).lower()
                    or search_text in str(e.get("item_name", "")).lower()
                ]
        except Exception:
            pass
        
        # Add rows
        for event in filtered_events:
            timestamp = self._format_timestamp(event.get("timestamp", ""))
            action = event.get("action", "unknown").replace("_", " ").title()
            source = event.get("source_label", "-")
            
            # Build details string
            details_parts = []
            if event.get("item_name"):
                details_parts.append(event["item_name"])
            if event.get("value") is not None:
                details_parts.append(f"Value: {event['value']}")
            if event.get("status"):
                details_parts.append(f"[{event['status']}]")
            details = " | ".join(details_parts) if details_parts else "-"
            
            table.add_row(timestamp, action, source, details)

    def _format_timestamp(self, iso_string: str) -> str:
        """Format ISO timestamp to human-readable format."""
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            return dt.strftime("%H:%M:%S")
        except Exception:
            return iso_string[:8] if iso_string else "-"

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle filter selection change."""
        if event.select.id == "type-filter":
            self.current_filter = event.value
            self._update_table()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input change."""
        if event.input.id == "search-input":
            self._update_table()

    def action_refresh(self) -> None:
        """Handle manual refresh action."""
        self.refresh_data()
        self.notify("History refreshed", timeout=2)

    def action_focus_filter(self) -> None:
        """Focus the search input."""
        try:
            search_input = self.query_one("#search-input", Input)
            search_input.focus()
        except Exception:
            pass


