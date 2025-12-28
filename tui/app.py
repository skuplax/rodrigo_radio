"""Main Textual application for Rodrigo Radio TUI Monitor."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from tui.screens.dashboard import DashboardScreen
from tui.screens.history import HistoryScreen
from tui.screens.stats import StatsScreen


class RodrigoRadioMonitor(App):
    """TUI Monitor for Rodrigo Radio."""

    TITLE = "Rodrigo Radio Monitor"
    SUB_TITLE = "Monitoring grandfather's music"
    
    CSS_PATH = "styles/app.tcss"
    
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("d", "switch_screen('dashboard')", "Dashboard", show=True),
        Binding("h", "switch_screen('history')", "History", show=True),
        Binding("s", "switch_screen('stats')", "Stats", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("?", "help", "Help"),
    ]
    
    SCREENS = {
        "dashboard": DashboardScreen,
        "history": HistoryScreen,
        "stats": StatsScreen,
    }

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.push_screen("dashboard")

    def action_switch_screen(self, screen_name: str) -> None:
        """Switch to a different screen."""
        if screen_name in self.SCREENS:
            self.switch_screen(screen_name)

    def action_refresh(self) -> None:
        """Force refresh the current screen."""
        screen = self.screen
        if hasattr(screen, "refresh_data"):
            screen.refresh_data()

    def action_help(self) -> None:
        """Show help information."""
        self.notify(
            "Keyboard shortcuts:\n"
            "d - Dashboard\n"
            "h - History\n"
            "s - Stats\n"
            "r - Refresh\n"
            "q - Quit",
            title="Help",
            timeout=5,
        )


def run_app():
    """Run the TUI application."""
    app = RodrigoRadioMonitor()
    app.run()


if __name__ == "__main__":
    run_app()


