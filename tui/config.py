"""Configuration for Rodrigo Radio TUI Monitor."""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class RefreshIntervals:
    """Refresh intervals for different data types."""
    events: float = 5.0        # Activity feed refresh (seconds)
    status: float = 3.0        # Player status refresh
    stats: float = 60.0        # Statistics refresh
    health: float = 30.0       # Health check refresh


@dataclass
class EventColors:
    """Color scheme for different event types."""
    playback_start: str = "green"
    source_change: str = "green"
    user_input: str = "yellow"
    audio: str = "cyan"
    network_error: str = "red"
    network_retry: str = "orange"
    system: str = "dim white"
    config: str = "blue"
    error: str = "red"
    default: str = "white"


@dataclass
class EventIcons:
    """Icons for different event types."""
    playback_start: str = "▶"
    source_change: str = "🔄"
    button_play_pause: str = "⏯"
    button_next: str = "⏭"
    button_previous: str = "⏮"
    button_cycle_source: str = "🔀"
    encoder_switch_press: str = "🔇"
    volume: str = "🔊"
    error: str = "❌"
    warning: str = "⚠"
    network: str = "🌐"
    startup: str = "🚀"
    shutdown: str = "⏹"
    default: str = "•"


@dataclass
class SourceIcons:
    """Icons for different source types."""
    spotify_playlist: str = "🎵"
    youtube_channel: str = "📺"
    youtube_playlist: str = "📺"
    default: str = "📻"


@dataclass
class StatusIcons:
    """Icons for status indicators."""
    playing: str = "▶"
    paused: str = "⏸"
    stopped: str = "⏹"
    loading: str = "⏳"
    connected: str = "🟢"
    disconnected: str = "🔴"
    reconnecting: str = "🟡"
    service_running: str = "✓"
    service_stopped: str = "✗"


@dataclass
class VolumeConfig:
    """Volume display configuration."""
    bar_width: int = 20
    bar_filled: str = "█"
    bar_empty: str = "░"
    high_threshold: int = 80
    medium_threshold: int = 50


@dataclass
class TUIConfig:
    """Main TUI configuration."""
    # Refresh intervals
    refresh: RefreshIntervals = field(default_factory=RefreshIntervals)
    
    # Colors
    colors: EventColors = field(default_factory=EventColors)
    
    # Icons
    event_icons: EventIcons = field(default_factory=EventIcons)
    source_icons: SourceIcons = field(default_factory=SourceIcons)
    status_icons: StatusIcons = field(default_factory=StatusIcons)
    
    # Volume display
    volume: VolumeConfig = field(default_factory=VolumeConfig)
    
    # Activity feed settings
    max_feed_events: int = 100
    
    # History settings
    default_history_limit: int = 200
    
    # Cache settings
    cache_ttl_seconds: int = 30
    
    # Timezone (default to Asia/Manila for Philippines)
    timezone: str = "Asia/Manila"
    
    @classmethod
    def from_env(cls) -> "TUIConfig":
        """Create config from environment variables."""
        config = cls()
        
        # Override from environment if set
        if os.getenv("TUI_REFRESH_EVENTS"):
            config.refresh.events = float(os.getenv("TUI_REFRESH_EVENTS"))
        if os.getenv("TUI_REFRESH_STATUS"):
            config.refresh.status = float(os.getenv("TUI_REFRESH_STATUS"))
        if os.getenv("TUI_MAX_FEED_EVENTS"):
            config.max_feed_events = int(os.getenv("TUI_MAX_FEED_EVENTS"))
        if os.getenv("TUI_TIMEZONE"):
            config.timezone = os.getenv("TUI_TIMEZONE")
        
        return config


# Global config instance
_config: Optional[TUIConfig] = None


def get_config() -> TUIConfig:
    """Get the global TUI configuration."""
    global _config
    if _config is None:
        _config = TUIConfig.from_env()
    return _config


def get_event_icon(action: str, event_type: str = "") -> str:
    """
    Get the appropriate icon for an event.
    
    Args:
        action: Event action name
        event_type: Event type (optional)
        
    Returns:
        Icon string
    """
    config = get_config()
    icons = config.event_icons
    
    # Map actions to icons
    action_map = {
        "playback_start": icons.playback_start,
        "source_change": icons.source_change,
        "button_play_pause": icons.button_play_pause,
        "button_next": icons.button_next,
        "button_previous": icons.button_previous,
        "button_cycle_source": icons.button_cycle_source,
        "encoder_switch_press": icons.encoder_switch_press,
        "volume_set": icons.volume,
        "volume_adjust": icons.volume,
        "mute": icons.encoder_switch_press,
        "unmute": icons.volume,
        "startup": icons.startup,
        "shutdown": icons.shutdown,
    }
    
    if action in action_map:
        return action_map[action]
    
    # Check event type for fallback
    if event_type == "network" or "network" in action.lower():
        return icons.network
    if event_type == "error" or "error" in action.lower():
        return icons.error
    if "warning" in action.lower():
        return icons.warning
    
    return icons.default


def get_event_color(action: str, event_type: str = "", status: str = "") -> str:
    """
    Get the appropriate color for an event.
    
    Args:
        action: Event action name
        event_type: Event type
        status: Event status
        
    Returns:
        Color name
    """
    config = get_config()
    colors = config.colors
    
    # Check status first
    if status in ("error", "failure"):
        return colors.error
    
    # Check event type
    if event_type == "user_input":
        return colors.user_input
    if event_type == "audio":
        return colors.audio
    if event_type == "network":
        if status == "retry":
            return colors.network_retry
        if status in ("error", "failure"):
            return colors.network_error
        return colors.default
    if event_type == "config":
        return colors.config
    if event_type == "system":
        if action in ("playback_start", "source_change"):
            return colors.playback_start
        return colors.system
    
    # Check action
    if action in ("playback_start", "source_change"):
        return colors.playback_start
    
    return colors.default


def get_source_icon(source_type: str) -> str:
    """
    Get the icon for a source type.
    
    Args:
        source_type: Source type (spotify_playlist, youtube_channel, etc.)
        
    Returns:
        Icon string
    """
    config = get_config()
    icons = config.source_icons
    
    type_map = {
        "spotify_playlist": icons.spotify_playlist,
        "youtube_channel": icons.youtube_channel,
        "youtube_playlist": icons.youtube_playlist,
    }
    
    return type_map.get(source_type, icons.default)


