"""Spotify playback backend using raspotify and Spotify Web API."""
import json
import logging
import random
import subprocess
import time
from pathlib import Path
from typing import Optional

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False

try:
    import dbus
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False

from backends.base import BaseBackend, BackendError
from utils.sound_feedback import (
    play_auth_error_beep,
    play_not_found_beep,
    play_device_error_beep,
    play_network_error_beep
)

logger = logging.getLogger(__name__)

# Configuration file path
# Try project directory first, then fall back to home directory for backwards compatibility
_PROJECT_DIR = Path(__file__).parent.parent.absolute()
if (_PROJECT_DIR / "config" / "spotify_api_config.json").exists() or (_PROJECT_DIR / "config" / "spotify_api_config.json.example").exists():
    CONFIG_FILE = _PROJECT_DIR / "config" / "spotify_api_config.json"
    CACHE_DIR = _PROJECT_DIR  # Cache in project root
else:
    CONFIG_FILE = Path.home() / "rodrigo_radio" / "spotify_api_config.json"
    CACHE_DIR = Path.home() / "rodrigo_radio"  # Cache in home directory


class SpotifyBackend(BaseBackend):
    """Spotify playback backend using raspotify and Spotify Web API."""
    
    def __init__(self):
        super().__init__()
        self._spotify: Optional[spotipy.Spotify] = None
        self._device_id: Optional[str] = None
        self._current_playlist_id: Optional[str] = None
        self._is_paused = False
        self._last_device_check = 0
        self._device_check_interval = 30  # Check for device every 30 seconds
        self._mpris_player = None  # MPRIS player object for fallback control
        self._device_activation_attempts = 0
        self._max_activation_attempts = 5  # Max attempts to activate device
        self._activation_retry_delay = 2.0  # Initial delay between activation attempts
        
        if not SPOTIPY_AVAILABLE:
            raise BackendError("spotipy is not installed. Install it with: pip3 install --user --break-system-packages spotipy")
        
        self._init_spotify()
        self._init_mpris()
    
    def _load_config(self) -> dict:
        """Load Spotify API configuration from file."""
        if not CONFIG_FILE.exists():
            raise BackendError(
                f"Spotify API config not found at {CONFIG_FILE}. "
                "Run spotify_oauth_setup.py to set up authentication."
            )
        
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            
            required_keys = ['client_id', 'client_secret', 'refresh_token']
            missing = [key for key in required_keys if key not in config]
            if missing:
                raise BackendError(f"Missing required config keys: {missing}")
            
            return config
        except json.JSONDecodeError as e:
            raise BackendError(f"Invalid JSON in config file: {e}")
        except Exception as e:
            raise BackendError(f"Error loading config: {e}")
    
    def _init_spotify(self):
        """Initialize Spotify client with OAuth."""
        try:
            config = self._load_config()
            
            cache_path = CACHE_DIR / ".spotify_cache"
            
            # Create OAuth manager
            auth_manager = SpotifyOAuth(
                client_id=config['client_id'],
                client_secret=config['client_secret'],
                redirect_uri=config.get('redirect_uri', 'http://127.0.0.1:8888/callback'),
                scope=config.get('scope', 'user-read-playback-state user-modify-playback-state user-read-currently-playing'),
                cache_path=str(cache_path)
            )
            
            # Ensure cache file has the refresh token from config
            # This handles cases where cache is missing or has stale data
            cached_token = auth_manager.get_cached_token()
            if not cached_token or 'refresh_token' not in cached_token:
                # Cache doesn't have refresh token, initialize it from config
                if 'refresh_token' in config:
                    token_data = {
                        'refresh_token': config['refresh_token'],
                        'scope': config.get('scope', 'user-read-playback-state user-modify-playback-state user-read-currently-playing')
                    }
                    # Write to cache file so spotipy can use it
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(cache_path, 'w') as f:
                        json.dump(token_data, f)
                    logger.info("Initialized cache file with refresh token from config")
            elif cached_token.get('refresh_token') != config.get('refresh_token'):
                # Cache has different refresh token, update it
                cached_token['refresh_token'] = config['refresh_token']
                with open(cache_path, 'w') as f:
                    json.dump(cached_token, f)
                logger.info("Updated cache file with refresh token from config")
            
            # Create Spotify client
            self._spotify = spotipy.Spotify(auth_manager=auth_manager)
            
            # Test authentication by making a simple API call
            try:
                self._spotify.current_user()
                logger.info("Initialized Spotify Web API client - authentication verified")
            except Exception as auth_error:
                logger.warning(f"Authentication test failed: {auth_error}. Token may need refresh.")
                # The auth_manager should handle refresh automatically on next API call
                
        except Exception as e:
            logger.error(f"Failed to initialize Spotify client: {e}")
            raise BackendError(f"Failed to initialize Spotify client: {e}")
    
    def _init_mpris(self):
        """Initialize MPRIS interface for fallback control."""
        if not DBUS_AVAILABLE:
            logger.debug("D-Bus not available, MPRIS fallback disabled")
            return
        
        try:
            bus = dbus.SessionBus()
            # Try to find raspotify/librespot MPRIS interface
            # Common service names: org.mpris.MediaPlayer2.raspotify, org.mpris.MediaPlayer2.librespot
            service_names = [
                'org.mpris.MediaPlayer2.raspotify',
                'org.mpris.MediaPlayer2.librespot',
                'org.mpris.MediaPlayer2.spotifyd'
            ]
            
            for service_name in service_names:
                try:
                    proxy = bus.get_object(service_name, '/org/mpris/MediaPlayer2')
                    self._mpris_player = dbus.Interface(proxy, 'org.mpris.MediaPlayer2.Player')
                    logger.info(f"MPRIS interface initialized: {service_name}")
                    return
                except dbus.exceptions.DBusException:
                    continue
            
            logger.debug("MPRIS interface not found (raspotify may not be running or MPRIS not enabled)")
        except Exception as e:
            logger.debug(f"Could not initialize MPRIS: {e}")
    
    def _check_raspotify_running(self) -> bool:
        """Check if raspotify service is running."""
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', '--quiet', 'raspotify'],
                timeout=2
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _find_raspotify_device(self, retry: bool = True) -> Optional[str]:
        """
        Find the raspotify device ID with automatic activation.
        
        Args:
            retry: If True, will retry with exponential backoff to activate device
            
        Returns:
            Device ID if found, None otherwise
        """
        try:
            if not self._spotify:
                return None
            
            try:
                devices = self._spotify.devices()
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 401:
                    logger.warning("Received 401 Unauthorized while finding device - attempting token refresh...")
                    try:
                        self._init_spotify()
                        devices = self._spotify.devices()
                    except Exception as refresh_error:
                        logger.error(f"Failed to refresh token: {refresh_error}")
                        return None
                else:
                    raise
            
            device_list = devices.get('devices', [])
            
            # Look for device with name containing raspotify-related keywords
            # Common names: "raspotify", "Raspberry Pi", "raspberry", "librespot", "Rodrigo's Radio", etc.
            keywords = ['raspotify', 'raspberry', 'librespot', 'pi', "rodrigo's radio", 'rodrigo radio']
            for device in device_list:
                name = device.get('name', '').lower()
                if any(keyword in name for keyword in keywords):
                    device_id = device.get('id')
                    if device_id:
                        logger.info(f"Found raspotify device: {device.get('name')} ({device_id})")
                        self._device_activation_attempts = 0  # Reset on success
                        return device_id
            
            # Device not found - try to activate it if raspotify is running
            if retry and self._check_raspotify_running():
                if self._device_activation_attempts < self._max_activation_attempts:
                    self._device_activation_attempts += 1
                    delay = self._activation_retry_delay * (2 ** (self._device_activation_attempts - 1))
                    logger.info(
                        f"Raspotify device not found in API (attempt {self._device_activation_attempts}/{self._max_activation_attempts}). "
                        f"Raspotify is running - waiting {delay:.1f}s for it to register with Spotify..."
                    )
                    time.sleep(delay)
                    # Retry finding the device
                    return self._find_raspotify_device(retry=True)
                else:
                    logger.warning(
                        f"Raspotify device not found after {self._max_activation_attempts} attempts. "
                        "Raspotify is running but not appearing in Spotify API. "
                        "This may require manual activation from Spotify app on first use."
                    )
            
            # If not found, log available devices for debugging
            if device_list:
                logger.debug("Raspotify device not found. Available devices:")
                for device in device_list:
                    logger.debug(f"  - {device.get('name')} ({device.get('id')})")
            else:
                logger.debug("No devices found in Spotify API")
            
            return None
        except Exception as e:
            logger.error(f"Error finding raspotify device: {e}")
            return None
    
    def _ensure_device(self, retry: bool = True) -> bool:
        """
        Ensure we have a valid device ID, refreshing if needed.
        Will automatically retry to activate device if not found.
        
        Args:
            retry: If True, will retry with exponential backoff to activate device
            
        Returns:
            True if device is available (or MPRIS fallback is available)
            
        Raises:
            BackendError: If device cannot be found and no fallback is available
        """
        current_time = time.time()
        
        # Check if we need to refresh device ID
        if not self._device_id or (current_time - self._last_device_check) > self._device_check_interval:
            self._device_id = self._find_raspotify_device(retry=retry)
            self._last_device_check = current_time
        
        if not self._device_id:
            if not self._check_raspotify_running():
                raise BackendError("raspotify service is not running. Start it with: sudo systemctl start raspotify")
            
            # If MPRIS is available, we can still control playback (but not start playlists)
            if self._mpris_player:
                logger.warning(
                    "Raspotify device not found in Spotify API, but MPRIS interface is available. "
                    "Basic controls (play/pause/next/previous) will work, but starting new playlists may fail. "
                    "The device should appear in the API after first manual connection from Spotify app."
                )
                return True  # Allow operation with MPRIS fallback
            
            play_device_error_beep()
            raise BackendError(
                "Raspotify device not found in Spotify API and MPRIS fallback unavailable. "
                "Raspotify is running, but it needs to be 'activated' first:\n"
                "1. Open Spotify app (mobile or desktop)\n"
                "2. Look for your Raspberry Pi device in the device list\n"
                "3. Connect to it (play something on it)\n"
                "4. Once connected, it will appear in the API and playback will work.\n"
                "Note: After first activation, the device should work automatically on subsequent boots."
            )
        
        return True
    
    def _normalize_uri(self, source_id: str) -> str:
        """Normalize source ID to full Spotify URI."""
        if source_id.startswith('spotify:'):
            return source_id
        
        # Try to detect type from format
        if ':' in source_id:
            # Already in format like "playlist:ID"
            return f"spotify:{source_id}"
        else:
            # Assume playlist if no type specified
            return f"spotify:playlist:{source_id}"
    
    def _get_track_count(self, uri: str) -> Optional[int]:
        """
        Get the total number of tracks in a playlist or album.
        
        Args:
            uri: Spotify URI (playlist, album, or track)
            
        Returns:
            Number of tracks, or None if unable to determine
        """
        try:
            if not self._spotify:
                return None
            
            # Extract type and ID from URI
            if not uri.startswith('spotify:'):
                return None
            
            parts = uri.split(':')
            if len(parts) < 3:
                return None
            
            uri_type = parts[1]  # 'playlist', 'album', 'track'
            uri_id = parts[2]
            
            if uri_type == 'track':
                # Single track, return 1
                return 1
            elif uri_type == 'playlist':
                # Get playlist tracks count
                try:
                    # Use playlist_tracks with limit=1 to get total count efficiently
                    result = self._spotify.playlist_tracks(uri_id, limit=1)
                    total = result.get('total', 0)
                    return total if total > 0 else None
                except Exception as e:
                    logger.debug(f"Could not get playlist track count: {e}")
                    return None
            elif uri_type == 'album':
                # Get album tracks count
                try:
                    album = self._spotify.album(uri_id)
                    tracks = album.get('tracks', {})
                    if isinstance(tracks, dict):
                        total = tracks.get('total', 0)
                        return total if total > 0 else None
                    return None
                except Exception as e:
                    logger.debug(f"Could not get album track count: {e}")
                    return None
            else:
                return None
        except Exception as e:
            logger.debug(f"Error getting track count: {e}")
            return None
    
    def play(self, source_id: str, **kwargs) -> bool:
        """
        Start playing a Spotify playlist, album, or track.
        
        Args:
            source_id: Playlist/album/track ID (can be full URI or just ID)
            **kwargs:
                - playlist_id: Playlist ID (alternative to source_id)
        """
        try:
            if not self._check_raspotify_running():
                raise BackendError("raspotify service is not running")
            
            if not self._spotify:
                raise BackendError("Spotify client not initialized")
            
            # Get URI to play
            playlist_id = kwargs.get('playlist_id') or source_id
            uri = self._normalize_uri(playlist_id)
            self._current_playlist_id = uri
            
            # Ensure we have a device (with automatic activation retries)
            self._ensure_device(retry=True)
            
            # Get track count and pick a random starting position for shuffle
            track_count = self._get_track_count(uri)
            random_offset = None
            if track_count and track_count > 1:
                # Pick a random track index (0-based)
                random_offset = random.randint(0, track_count - 1)
                logger.info(f"Starting playback from random track {random_offset + 1} of {track_count}")
            
            # Start playback
            try:
                if random_offset is not None:
                    # Start from random position
                    self._spotify.start_playback(
                        device_id=self._device_id,
                        context_uri=uri,
                        offset={'position': random_offset}
                    )
                    logger.info(f"Started playback from random position: {uri}")
                else:
                    # Start from beginning (single track or couldn't get count)
                    self._spotify.start_playback(device_id=self._device_id, context_uri=uri)
                    logger.info(f"Started playback: {uri}")
                
                # Enable shuffle mode
                try:
                    self._spotify.shuffle(state=True, device_id=self._device_id)
                    logger.info("Shuffle mode enabled")
                except Exception as shuffle_error:
                    logger.warning(f"Could not enable shuffle mode: {shuffle_error}")
                    # Continue anyway - playback started successfully
                
                self.set_playing_state(True)
                self._is_paused = False
                
                # Try to get current track info
                time.sleep(1)  # Wait a bit for playback to start
                self._update_current_item()
                
                return True
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 401:
                    # Token expired or invalid - try to refresh
                    logger.warning("Received 401 Unauthorized - token may be expired, attempting refresh...")
                    try:
                        # Reinitialize Spotify client to trigger token refresh
                        self._init_spotify()
                        
                        # Get track count and pick a random starting position for shuffle
                        track_count = self._get_track_count(uri)
                        random_offset = None
                        if track_count and track_count > 1:
                            random_offset = random.randint(0, track_count - 1)
                            logger.info(f"Starting playback from random track {random_offset + 1} of {track_count} (after refresh)")
                        
                        # Retry playback
                        if random_offset is not None:
                            self._spotify.start_playback(
                                device_id=self._device_id,
                                context_uri=uri,
                                offset={'position': random_offset}
                            )
                            logger.info(f"Started playback from random position after token refresh: {uri}")
                        else:
                            self._spotify.start_playback(device_id=self._device_id, context_uri=uri)
                            logger.info(f"Started playback after token refresh: {uri}")
                        
                        # Enable shuffle mode
                        try:
                            self._spotify.shuffle(state=True, device_id=self._device_id)
                            logger.info("Shuffle mode enabled after token refresh")
                        except Exception as shuffle_error:
                            logger.warning(f"Could not enable shuffle mode: {shuffle_error}")
                        
                        self.set_playing_state(True)
                        self._is_paused = False
                        time.sleep(1)
                        self._update_current_item()
                        return True
                    except Exception as refresh_error:
                        play_auth_error_beep()
                        raise BackendError(
                            f"Authentication failed and token refresh unsuccessful: {refresh_error}. "
                            "You may need to run spotify_oauth_setup.py again to re-authenticate."
                        )
                elif e.http_status == 404:
                    play_not_found_beep()
                    raise BackendError(f"Playlist/album/track not found: {uri}")
                elif e.http_status == 403:
                    raise BackendError("Permission denied. Make sure your Spotify account has Premium.")
                elif e.http_status == 404 and 'device' in str(e).lower():
                    # Device not found error - try to reactivate
                    logger.warning("Device not found during playback, attempting to reactivate...")
                    self._device_id = None  # Force refresh
                    self._ensure_device(retry=True)
                    # Retry playback once
                    try:
                        # Get track count and pick a random starting position for shuffle
                        track_count = self._get_track_count(uri)
                        random_offset = None
                        if track_count and track_count > 1:
                            random_offset = random.randint(0, track_count - 1)
                            logger.info(f"Starting playback from random track {random_offset + 1} of {track_count} (after reactivation)")
                        
                        if random_offset is not None:
                            self._spotify.start_playback(
                                device_id=self._device_id,
                                context_uri=uri,
                                offset={'position': random_offset}
                            )
                            logger.info(f"Started playback from random position after reactivation: {uri}")
                        else:
                            self._spotify.start_playback(device_id=self._device_id, context_uri=uri)
                            logger.info(f"Started playback after reactivation: {uri}")
                        
                        # Enable shuffle mode
                        try:
                            self._spotify.shuffle(state=True, device_id=self._device_id)
                            logger.info("Shuffle mode enabled after reactivation")
                        except Exception as shuffle_error:
                            logger.warning(f"Could not enable shuffle mode: {shuffle_error}")
                        
                        self.set_playing_state(True)
                        self._is_paused = False
                        time.sleep(1)
                        self._update_current_item()
                        return True
                    except Exception as retry_e:
                        raise BackendError(f"Failed to start playback after reactivation: {retry_e}")
                else:
                    raise BackendError(f"Spotify API error: {e}")
                    
        except BackendError:
            raise
        except Exception as e:
            # Check if it's a network-related error
            error_str = str(e).lower()
            error_type = type(e).__name__.lower()
            
            if any(keyword in error_str or keyword in error_type for keyword in 
                   ['network', 'connection', 'timeout', 'dns', 'socket', 'urlerror', 'requests']):
                play_network_error_beep()
            else:
                # For other errors, play connection error (handled by player_controller)
                pass
            
            logger.error(f"Error in play(): {e}")
            self.set_playing_state(False)
            raise BackendError(f"Failed to start playback: {e}")
    
    def pause(self) -> bool:
        """Pause playback."""
        try:
            # Try Web API first
            if self._spotify and self._device_id:
                try:
                    self._spotify.pause_playback(device_id=self._device_id)
                    self._is_paused = True
                    # Keep _is_playing = True (we have a track, just paused)
                    # Don't set it to False, as that would indicate stopped, not paused
                    logger.info("Paused Spotify playback (Web API)")
                    return True
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 401:
                        logger.debug("Received 401 Unauthorized during pause - attempting token refresh...")
                        try:
                            self._init_spotify()
                            self._spotify.pause_playback(device_id=self._device_id)
                            self._is_paused = True
                            logger.info("Paused Spotify playback (Web API) after token refresh")
                            return True
                        except Exception:
                            logger.debug("Web API pause failed after token refresh, trying MPRIS fallback")
                    else:
                        logger.debug(f"Web API pause failed: {e}, trying MPRIS fallback")
                except Exception as e:
                    logger.debug(f"Web API pause failed: {e}, trying MPRIS fallback")
            
            # Fallback to MPRIS
            if self._mpris_player:
                try:
                    self._mpris_player.Pause()
                    self._is_paused = True
                    # Keep _is_playing = True (we have a track, just paused)
                    logger.info("Paused Spotify playback (MPRIS)")
                    return True
                except Exception as e:
                    logger.debug(f"MPRIS pause failed: {e}")
            
            return False
        except Exception as e:
            logger.error(f"Error pausing: {e}")
            return False
    
    def resume(self) -> bool:
        """Resume playback."""
        try:
            # Try Web API first
            if self._spotify and self._device_id:
                try:
                    self._spotify.start_playback(device_id=self._device_id)
                    self._is_paused = False
                    self.set_playing_state(True)
                    logger.info("Resumed Spotify playback (Web API)")
                    return True
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 401:
                        logger.debug("Received 401 Unauthorized during resume - attempting token refresh...")
                        try:
                            self._init_spotify()
                            self._spotify.start_playback(device_id=self._device_id)
                            self._is_paused = False
                            self.set_playing_state(True)
                            logger.info("Resumed Spotify playback (Web API) after token refresh")
                            return True
                        except Exception:
                            logger.debug("Web API resume failed after token refresh, trying MPRIS fallback")
                    else:
                        logger.debug(f"Web API resume failed: {e}, trying MPRIS fallback")
                except Exception as e:
                    logger.debug(f"Web API resume failed: {e}, trying MPRIS fallback")
            
            # Fallback to MPRIS
            if self._mpris_player:
                try:
                    self._mpris_player.Play()
                    self._is_paused = False
                    self.set_playing_state(True)
                    logger.info("Resumed Spotify playback (MPRIS)")
                    return True
                except Exception as e:
                    logger.debug(f"MPRIS resume failed: {e}")
            
            return False
        except Exception as e:
            logger.error(f"Error resuming: {e}")
            return False
    
    def stop(self) -> bool:
        """Stop playback completely."""
        try:
            if not self._spotify:
                return True  # Already stopped
            
            try:
                self._ensure_device()
                # Pause playback to stop it
                try:
                    self._spotify.pause_playback(device_id=self._device_id)
                    logger.info("Paused Spotify playback (stop)")
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 401:
                        logger.debug("Received 401 Unauthorized during stop pause - attempting token refresh...")
                        try:
                            self._init_spotify()
                            self._spotify.pause_playback(device_id=self._device_id)
                            logger.info("Paused Spotify playback (stop) after token refresh")
                        except Exception:
                            logger.debug("Could not pause during stop after token refresh")
                    else:
                        raise
                
                # Wait a moment and verify it's actually stopped
                time.sleep(0.2)
                
                # Check if it's still playing and force stop if needed
                try:
                    playback = self._spotify.current_playback()
                    if playback and playback.get('is_playing', False):
                        # Still playing, try to pause again more aggressively
                        logger.warning("Spotify still playing after pause, forcing stop...")
                        self._spotify.pause_playback(device_id=self._device_id)
                        time.sleep(0.2)
                        
                        # Check one more time
                        playback = self._spotify.current_playback()
                        if playback and playback.get('is_playing', False):
                            logger.error("Spotify still playing after multiple stop attempts!")
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 401:
                        logger.debug("Received 401 Unauthorized during stop - token may need refresh")
                        # Try to refresh and continue
                        try:
                            self._init_spotify()
                        except Exception:
                            pass  # Continue anyway
                    else:
                        logger.debug(f"Could not verify stop status: {e}")
                except Exception as e:
                    logger.debug(f"Could not verify stop status: {e}")
                    
            except Exception as e:
                # If pause fails, log but continue - device might not be available
                logger.debug(f"Could not pause during stop (may already be stopped): {e}")
            
            self.set_playing_state(False)
            self._is_paused = False
            self.set_current_item(None)
            self._current_playlist_id = None
            logger.info("Stopped Spotify playback")
            return True
        except Exception as e:
            logger.error(f"Error stopping: {e}")
            return False
    
    def next(self) -> bool:
        """Skip to next track."""
        try:
            # Try Web API first
            if self._spotify and self._device_id:
                try:
                    self._spotify.next_track(device_id=self._device_id)
                    logger.info("Skipped to next track (Web API)")
                    time.sleep(0.5)
                    self._update_current_item()
                    return True
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 401:
                        logger.debug("Received 401 Unauthorized during next - attempting token refresh...")
                        try:
                            self._init_spotify()
                            self._spotify.next_track(device_id=self._device_id)
                            logger.info("Skipped to next track (Web API) after token refresh")
                            time.sleep(0.5)
                            self._update_current_item()
                            return True
                        except Exception:
                            logger.debug("Web API next failed after token refresh, trying MPRIS fallback")
                    else:
                        logger.debug(f"Web API next failed: {e}, trying MPRIS fallback")
                except Exception as e:
                    logger.debug(f"Web API next failed: {e}, trying MPRIS fallback")
            
            # Fallback to MPRIS
            if self._mpris_player:
                try:
                    self._mpris_player.Next()
                    logger.info("Skipped to next track (MPRIS)")
                    time.sleep(0.5)
                    self._update_current_item()
                    return True
                except Exception as e:
                    logger.debug(f"MPRIS next failed: {e}")
            
            return False
        except Exception as e:
            logger.error(f"Error skipping: {e}")
            return False
    
    def previous(self) -> bool:
        """Go to previous track."""
        try:
            # Try Web API first
            if self._spotify and self._device_id:
                try:
                    self._spotify.previous_track(device_id=self._device_id)
                    logger.info("Went to previous track (Web API)")
                    time.sleep(0.5)
                    self._update_current_item()
                    return True
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 401:
                        logger.debug("Received 401 Unauthorized during previous - attempting token refresh...")
                        try:
                            self._init_spotify()
                            self._spotify.previous_track(device_id=self._device_id)
                            logger.info("Went to previous track (Web API) after token refresh")
                            time.sleep(0.5)
                            self._update_current_item()
                            return True
                        except Exception:
                            logger.debug("Web API previous failed after token refresh, trying MPRIS fallback")
                    else:
                        logger.debug(f"Web API previous failed: {e}, trying MPRIS fallback")
                except Exception as e:
                    logger.debug(f"Web API previous failed: {e}, trying MPRIS fallback")
            
            # Fallback to MPRIS
            if self._mpris_player:
                try:
                    self._mpris_player.Previous()
                    logger.info("Went to previous track (MPRIS)")
                    time.sleep(0.5)
                    self._update_current_item()
                    return True
                except Exception as e:
                    logger.debug(f"MPRIS previous failed: {e}")
            
            return False
        except Exception as e:
            logger.error(f"Error going to previous: {e}")
            return False
    
    def _update_current_item(self):
        """Update current track information."""
        try:
            if not self._spotify:
                return
            
            try:
                playback = self._spotify.current_playback()
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 401:
                    logger.debug("Received 401 Unauthorized while updating current item - attempting token refresh...")
                    try:
                        self._init_spotify()
                        playback = self._spotify.current_playback()
                    except Exception:
                        # If refresh fails, just skip updating current item
                        return
                else:
                    # For other errors, just skip updating
                    return
            
            if playback and playback.get('item'):
                item = playback['item']
                title = item.get('name', 'Unknown')
                artists = [artist['name'] for artist in item.get('artists', [])]
                artist_str = ', '.join(artists) if artists else 'Unknown'
                self.set_current_item(f"{artist_str} - {title}")
            else:
                self.set_current_item(None)
        except Exception as e:
            logger.debug(f"Could not update current item: {e}")
            # Don't fail if we can't get track info
    
    def is_playing(self) -> bool:
        """Check if currently playing (and not paused)."""
        try:
            # Check internal paused state first - if we're paused, return False immediately
            # This prevents race conditions where API hasn't updated yet
            if self._is_paused:
                return False
            
            # Try Web API first
            if self._spotify:
                try:
                    playback = self._spotify.current_playback()
                    if playback:
                        is_playing = playback.get('is_playing', False)
                        self.set_playing_state(is_playing)
                        # Only update _is_paused if API says we're not playing
                        # Don't overwrite if we just paused (API might be stale)
                        if not is_playing:
                            self._is_paused = True
                        return is_playing
                    else:
                        self.set_playing_state(False)
                        return False
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 401:
                        logger.debug("Received 401 Unauthorized while checking playback state - attempting token refresh...")
                        try:
                            self._init_spotify()
                            # Retry once after refresh
                            playback = self._spotify.current_playback()
                            if playback:
                                is_playing = playback.get('is_playing', False)
                                self.set_playing_state(is_playing)
                                if not is_playing:
                                    self._is_paused = True
                                return is_playing
                            else:
                                self.set_playing_state(False)
                                return False
                        except Exception:
                            pass  # Fall through to MPRIS
                    else:
                        pass  # Fall through to MPRIS
                except Exception:
                    pass  # Fall through to MPRIS
            
            # Fallback to MPRIS
            if self._mpris_player:
                try:
                    # Get playback status via Properties interface
                    props = dbus.Interface(self._mpris_player, 'org.freedesktop.DBus.Properties')
                    playback_status = props.Get('org.mpris.MediaPlayer2.Player', 'PlaybackStatus')
                    is_playing = (playback_status == 'Playing')
                    self.set_playing_state(is_playing)
                    # Only update _is_paused if MPRIS says we're not playing
                    if not is_playing:
                        self._is_paused = True
                    return is_playing
                except Exception:
                    pass  # Fall through to internal state
            
            # Fallback to internal state
            return self._is_playing and not self._is_paused
        except Exception:
            return self._is_playing and not self._is_paused
