"""Volume bar widget for Rodrigo Radio TUI Monitor."""

from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.reactive import reactive

from tui.services.player_status import PlayerStatusService
from tui.config import get_config


class VolumeBarWidget(Static):
    """Widget displaying current volume level."""

    DEFAULT_CSS = """
    VolumeBarWidget {
        height: 5;
        padding: 1;
        border: solid $warning;
        background: $surface-darken-1;
    }
    
    VolumeBarWidget .widget-title {
        text-style: bold;
        color: $warning;
    }
    
    VolumeBarWidget .volume-high {
        color: $error;
    }
    
    VolumeBarWidget .volume-medium {
        color: $warning;
    }
    
    VolumeBarWidget .volume-low {
        color: $success;
    }
    
    VolumeBarWidget .volume-muted {
        color: $text-muted;
        text-style: italic;
    }
    
    VolumeBarWidget .time-mode {
        color: $text-muted;
        text-style: italic;
    }
    """

    volume = reactive(0)
    is_muted = reactive(False)
    time_mode = reactive("day")
    db_value = reactive(0.0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player_status = PlayerStatusService()

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Label("🔊 VOLUME", classes="widget-title")
        yield Static("", id="volume-bar-display")
        yield Static("", id="time-mode-display", classes="time-mode")

    def on_mount(self) -> None:
        """Initialize widget on mount."""
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh volume data."""
        volume_info = self.player_status.get_volume_info()
        
        if volume_info:
            self.volume = volume_info.get("percentage", 0) or 0
            self.is_muted = volume_info.get("muted", False)
            self.db_value = volume_info.get("db", 0.0) or 0.0
        else:
            self.volume = 0
            self.is_muted = False
            self.db_value = 0.0
        
        self.time_mode = self.player_status.get_time_volume_mode()
        
        self._update_display()

    def _update_display(self) -> None:
        """Update the display."""
        config = get_config()
        vol_config = config.volume
        
        # Build volume bar
        bar_width = vol_config.bar_width
        filled = int((self.volume / 100) * bar_width)
        empty = bar_width - filled
        
        bar_filled = vol_config.bar_filled * filled
        bar_empty = vol_config.bar_empty * empty
        
        # Determine color class based on volume level
        if self.is_muted:
            color_class = "volume-muted"
            volume_str = "MUTED"
        elif self.volume >= vol_config.high_threshold:
            color_class = "volume-high"
            volume_str = f"{self.volume}%"
        elif self.volume >= vol_config.medium_threshold:
            color_class = "volume-medium"
            volume_str = f"{self.volume}%"
        else:
            color_class = "volume-low"
            volume_str = f"{self.volume}%"
        
        try:
            bar_display = self.query_one("#volume-bar-display", Static)
            
            if self.is_muted:
                bar_display.update(f"🔇 [{bar_empty}] {volume_str}")
            else:
                bar_display.update(f"🔊 [{bar_filled}{bar_empty}] {volume_str}")
            
            # Update color classes
            bar_display.remove_class("volume-high", "volume-medium", "volume-low", "volume-muted")
            bar_display.add_class(color_class)
        except Exception:
            pass
        
        # Time mode display
        try:
            mode_display = self.query_one("#time-mode-display", Static)
            mode_icons = {
                "day": "☀️",
                "evening": "🌅",
                "night": "🌙",
            }
            mode_icon = mode_icons.get(self.time_mode, "")
            mode_text = self.time_mode.capitalize()
            
            mode_display.update(f"{mode_icon} {mode_text} Mode")
        except Exception:
            pass

    def watch_volume(self, value: int) -> None:
        """React to volume changes."""
        self._update_display()

    def watch_is_muted(self, value: bool) -> None:
        """React to mute state changes."""
        self._update_display()

    def watch_time_mode(self, value: str) -> None:
        """React to time mode changes."""
        self._update_display()


