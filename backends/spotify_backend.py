"""Spotify playback backend using spotifyd."""
import subprocess
import logging
import dbus
import dbus.exceptions
from typing import Optional
from backends.base import BaseBackend, BackendError

logger = logging.getLogger(__name__)

# Try to use D-Bus, fall back to CLI if not available
try:
    import dbus
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
    logger.warning("dbus-python not available, will use CLI fallback")


class SpotifyBackend(BaseBackend):
    """Spotify playback backend using spotifyd."""
    
    def __init__(self):
        super().__init__()
        self._dbus_available = DBUS_AVAILABLE
        self._dbus_bus = None
        self._dbus_player = None
        self._current_playlist_id: Optional[str] = None
        self._is_paused = False
        
        if self._dbus_available:
            self._init_dbus()
    
    def _init_dbus(self):
        """Initialize D-Bus connection to spotifyd."""
        try:
            self._dbus_bus = dbus.SessionBus()
            spotifyd_object = self._dbus_bus.get_object(
                'org.mpris.MediaPlayer2.spotifyd',
                '/org/mpris/MediaPlayer2'
            )
            self._dbus_player = dbus.Interface(
                spotifyd_object,
                'org.mpris.MediaPlayer2.Player'
            )
            logger.info("Connected to spotifyd via D-Bus")
        except dbus.exceptions.DBusException as e:
            logger.warning(f"Could not connect to spotifyd via D-Bus: {e}")
            logger.info("Falling back to CLI control")
            self._dbus_available = False
            self._dbus_bus = None
            self._dbus_player = None
    
    def _check_spotifyd_running(self) -> bool:
        """Check if spotifyd is running."""
        try:
            result = subprocess.run(
                ['systemctl', '--user', 'is-active', '--quiet', 'spotifyd'],
                timeout=2
            )
            return result.returncode == 0
        except Exception:
            # Try system-wide service
            try:
                result = subprocess.run(
                    ['systemctl', 'is-active', '--quiet', 'spotifyd'],
                    timeout=2
                )
                return result.returncode == 0
            except Exception:
                return False
    
    def _play_uri_dbus(self, uri: str) -> bool:
        """Play a Spotify URI using D-Bus."""
        try:
            if not self._dbus_player:
                return False
            
            self._dbus_player.OpenUri(uri)
            logger.info(f"Started playback via D-Bus: {uri}")
            return True
        except Exception as e:
            logger.error(f"Error playing via D-Bus: {e}")
            return False
    
    def _play_uri_cli(self, uri: str) -> bool:
        """Play a Spotify URI using CLI (dbus-send)."""
        try:
            cmd = [
                'dbus-send',
                '--print-reply',
                '--dest=org.mpris.MediaPlayer2.spotifyd',
                '/org/mpris/MediaPlayer2',
                'org.mpris.MediaPlayer2.Player.OpenUri',
                f'string:{uri}'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.info(f"Started playback via CLI: {uri}")
                return True
            else:
                logger.error(f"CLI playback failed: {result.stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"Error playing via CLI: {e}")
            return False
    
    def _get_playback_status_dbus(self) -> Optional[str]:
        """Get current playback status via D-Bus."""
        try:
            if not self._dbus_player:
                return None
            
            status = self._dbus_player.Get(
                'org.mpris.MediaPlayer2.Player',
                'PlaybackStatus',
                dbus_interface='org.freedesktop.DBus.Properties'
            )
            return str(status)
        except Exception:
            return None
    
    def _get_current_track_dbus(self) -> Optional[str]:
        """Get current track name via D-Bus."""
        try:
            if not self._dbus_player:
                return None
            
            metadata = self._dbus_player.Get(
                'org.mpris.MediaPlayer2.Player',
                'Metadata',
                dbus_interface='org.freedesktop.DBus.Properties'
            )
            
            if 'xesam:title' in metadata:
                title = str(metadata['xesam:title'])
                artist = str(metadata.get('xesam:artist', ['Unknown'])[0])
                return f"{artist} - {title}"
            return None
        except Exception:
            return None
    
    def play(self, source_id: str, **kwargs) -> bool:
        """
        Start playing a Spotify playlist.
        
        Args:
            source_id: Playlist ID (can be full URI or just ID)
            **kwargs:
                - playlist_id: Playlist ID (alternative to source_id)
        """
        try:
            if not self._check_spotifyd_running():
                raise BackendError("spotifyd is not running")
            
            playlist_id = kwargs.get('playlist_id') or source_id
            
            # Ensure it's a full Spotify URI
            if not playlist_id.startswith('spotify:'):
                if ':' in playlist_id:
                    # Assume it's already a URI format
                    uri = f"spotify:{playlist_id}"
                else:
                    uri = f"spotify:playlist:{playlist_id}"
            else:
                uri = playlist_id
            
            self._current_playlist_id = uri
            
            # Try D-Bus first, fall back to CLI
            success = False
            if self._dbus_available and self._dbus_player:
                success = self._play_uri_dbus(uri)
            
            if not success:
                success = self._play_uri_cli(uri)
            
            if success:
                self.set_playing_state(True)
                self._is_paused = False
                
                # Try to get track name
                if self._dbus_available:
                    track_name = self._get_current_track_dbus()
                    if track_name:
                        self.set_current_item(track_name)
                    else:
                        self.set_current_item("Spotify Playlist")
                else:
                    self.set_current_item("Spotify Playlist")
                
                return True
            else:
                raise BackendError("Failed to start Spotify playback")
                
        except Exception as e:
            logger.error(f"Error in play(): {e}")
            self.set_playing_state(False)
            return False
    
    def pause(self) -> bool:
        """Pause playback."""
        try:
            if not self._check_spotifyd_running():
                return False
            
            if self._dbus_available and self._dbus_player:
                try:
                    self._dbus_player.Pause()
                    self._is_paused = True
                    logger.info("Paused Spotify playback")
                    return True
                except Exception as e:
                    logger.error(f"Error pausing via D-Bus: {e}")
            
            # CLI fallback
            cmd = [
                'dbus-send',
                '--print-reply',
                '--dest=org.mpris.MediaPlayer2.spotifyd',
                '/org/mpris/MediaPlayer2',
                'org.mpris.MediaPlayer2.Player.Pause'
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=2)
            if result.returncode == 0:
                self._is_paused = True
                logger.info("Paused Spotify playback via CLI")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error pausing: {e}")
            return False
    
    def resume(self) -> bool:
        """Resume playback."""
        try:
            if not self._check_spotifyd_running():
                return False
            
            if self._dbus_available and self._dbus_player:
                try:
                    self._dbus_player.Play()
                    self._is_paused = False
                    logger.info("Resumed Spotify playback")
                    return True
                except Exception as e:
                    logger.error(f"Error resuming via D-Bus: {e}")
            
            # CLI fallback
            cmd = [
                'dbus-send',
                '--print-reply',
                '--dest=org.mpris.MediaPlayer2.spotifyd',
                '/org/mpris/MediaPlayer2',
                'org.mpris.MediaPlayer2.Player.Play'
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=2)
            if result.returncode == 0:
                self._is_paused = False
                logger.info("Resumed Spotify playback via CLI")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error resuming: {e}")
            return False
    
    def stop(self) -> bool:
        """Stop playback."""
        try:
            if not self._check_spotifyd_running():
                return True  # Already stopped
            
            if self._dbus_available and self._dbus_player:
                try:
                    self._dbus_player.Stop()
                    logger.info("Stopped Spotify playback")
                    self.set_playing_state(False)
                    self._is_paused = False
                    self.set_current_item(None)
                    return True
                except Exception as e:
                    logger.error(f"Error stopping via D-Bus: {e}")
            
            # CLI fallback
            cmd = [
                'dbus-send',
                '--print-reply',
                '--dest=org.mpris.MediaPlayer2.spotifyd',
                '/org/mpris/MediaPlayer2',
                'org.mpris.MediaPlayer2.Player.Stop'
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=2)
            if result.returncode == 0:
                logger.info("Stopped Spotify playback via CLI")
                self.set_playing_state(False)
                self._is_paused = False
                self.set_current_item(None)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error stopping: {e}")
            return False
    
    def next(self) -> bool:
        """Skip to next track."""
        try:
            if not self._check_spotifyd_running():
                return False
            
            if self._dbus_available and self._dbus_player:
                try:
                    self._dbus_player.Next()
                    logger.info("Skipped to next track")
                    # Update current item
                    track_name = self._get_current_track_dbus()
                    if track_name:
                        self.set_current_item(track_name)
                    return True
                except Exception as e:
                    logger.error(f"Error skipping via D-Bus: {e}")
            
            # CLI fallback
            cmd = [
                'dbus-send',
                '--print-reply',
                '--dest=org.mpris.MediaPlayer2.spotifyd',
                '/org/mpris/MediaPlayer2',
                'org.mpris.MediaPlayer2.Player.Next'
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=2)
            if result.returncode == 0:
                logger.info("Skipped to next track via CLI")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error skipping: {e}")
            return False
    
    def previous(self) -> bool:
        """Go to previous track."""
        try:
            if not self._check_spotifyd_running():
                return False
            
            if self._dbus_available and self._dbus_player:
                try:
                    self._dbus_player.Previous()
                    logger.info("Went to previous track")
                    # Update current item
                    track_name = self._get_current_track_dbus()
                    if track_name:
                        self.set_current_item(track_name)
                    return True
                except Exception as e:
                    logger.error(f"Error going to previous via D-Bus: {e}")
            
            # CLI fallback
            cmd = [
                'dbus-send',
                '--print-reply',
                '--dest=org.mpris.MediaPlayer2.spotifyd',
                '/org/mpris/MediaPlayer2',
                'org.mpris.MediaPlayer2.Player.Previous'
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=2)
            if result.returncode == 0:
                logger.info("Went to previous track via CLI")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error going to previous: {e}")
            return False
    
    def is_playing(self) -> bool:
        """Check if currently playing (and not paused)."""
        try:
            if not self._check_spotifyd_running():
                return False
            
            if self._dbus_available:
                status = self._get_playback_status_dbus()
                if status == 'Playing':
                    self.set_playing_state(True)
                    self._is_paused = False
                    return True
                elif status == 'Paused':
                    self.set_playing_state(True)
                    self._is_paused = True
                    return False
                else:
                    self.set_playing_state(False)
                    return False
            
            # Fallback: assume state from our internal tracking
            return self._is_playing and not self._is_paused
            
        except Exception:
            return False

