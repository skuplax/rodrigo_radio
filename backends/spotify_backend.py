"""Spotify playback backend using raspotify and Spotify Web API."""
import json
import logging
import random
import subprocess
import threading
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
    play_network_error_beep,
    play_retry_beep
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
        self._monitoring_active = False
        self._monitoring_thread: Optional[threading.Thread] = None
        self._was_playing = False  # Track previous playing state to detect natural end
        self._last_track_item_id: Optional[str] = None  # Track the last track's Spotify ID to detect changes
        self._auth_manager: Optional[SpotifyOAuth] = None  # Store auth manager for proactive refresh
        self._token_refresh_thread: Optional[threading.Thread] = None
        self._token_refresh_active = False
        self._last_token_refresh = 0
        self._token_refresh_interval = 3 * 24 * 3600  # Refresh every 3 days (tokens expire after ~60 days of inactivity, so 3 days provides good safety margin)
        self._last_api_call = 0  # Track last API call time for rate limiting
        self._min_api_call_interval = 0.2  # Minimum seconds between API calls (200ms)
        self._rate_limit_backoff = 1.0  # Current backoff delay for rate limits (starts at 1 second)
        self._max_rate_limit_backoff = 60.0  # Maximum backoff delay (60 seconds)
        self._last_raspotify_restart = 0  # Track last restart time to avoid restart loops
        self._raspotify_restart_cooldown = 30.0  # Minimum seconds between restarts (30 seconds)
        
        if not SPOTIPY_AVAILABLE:
            raise BackendError("spotipy is not installed. Install it with: pip3 install --user --break-system-packages spotipy")
        
        self._init_spotify()
        self._init_mpris()
        self._start_token_refresh_thread()
    
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
            
            # Store config for device lookup
            self._config = config
            
            return config
        except json.JSONDecodeError as e:
            raise BackendError(f"Invalid JSON in config file: {e}")
        except Exception as e:
            raise BackendError(f"Error loading config: {e}")
    
    def _init_spotify(self):
        """Initialize Spotify client with OAuth."""
        try:
            config = self._load_config()  # This already stores config in self._config
            
            cache_path = CACHE_DIR / ".spotify_cache"
            
            # Create OAuth manager
            auth_manager = SpotifyOAuth(
                client_id=config['client_id'],
                client_secret=config['client_secret'],
                redirect_uri=config.get('redirect_uri', 'http://127.0.0.1:8888/callback'),
                scope=config.get('scope', 'user-read-playback-state user-modify-playback-state user-read-currently-playing'),
                cache_path=str(cache_path)
            )
            
            # Store auth manager for proactive token refresh
            self._auth_manager = auth_manager
            
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
                self._last_token_refresh = time.time()
            except Exception as auth_error:
                error_str = str(auth_error).lower()
                # Check if refresh token has expired
                if 'invalid_grant' in error_str or 'refresh_token' in error_str and ('expired' in error_str or 'invalid' in error_str):
                    logger.error(
                        "Refresh token has expired. You need to re-authenticate:\n"
                        f"  Run: python3 {Path(__file__).parent.parent / 'scripts' / 'spotify_oauth_setup.py'}\n"
                        "This will generate a new refresh token. Refresh tokens expire after ~60 days of inactivity."
                    )
                    raise BackendError("Spotify refresh token has expired. Please run spotify_oauth_setup.py to re-authenticate.")
                else:
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
    
    def _restart_raspotify_service(self) -> bool:
        """
        Restart the raspotify service.
        
        Returns:
            True if service was restarted successfully, False otherwise
        """
        current_time = time.time()
        
        # Check cooldown to avoid restart loops
        if current_time - self._last_raspotify_restart < self._raspotify_restart_cooldown:
            logger.debug(f"Raspotify restart cooldown active (restarted {current_time - self._last_raspotify_restart:.1f}s ago)")
            return False
        
        logger.info("Restarting raspotify service to resolve connection issues...")
        
        try:
            # Stop the service first
            result = subprocess.run(
                ['systemctl', 'stop', 'raspotify'],
                timeout=10,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.warning(f"Failed to stop raspotify: {result.stderr or result.stdout}")
                # Continue anyway - might already be stopped
            
            # Wait a moment for it to fully stop
            time.sleep(1.0)
            
            # Start the service
            result = subprocess.run(
                ['systemctl', 'start', 'raspotify'],
                timeout=10,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Give the service time to start and register with Spotify
                logger.info("Waiting for raspotify to restart and register with Spotify API...")
                for i in range(5):  # Wait up to 5 seconds
                    time.sleep(1)
                    if self._check_raspotify_running():
                        logger.info(f"Successfully restarted raspotify service (verified after {i+1}s)")
                        self._last_raspotify_restart = time.time()
                        # Reset device ID so it will be re-discovered
                        self._device_id = None
                        self._last_device_check = 0
                        return True
                
                # Final check
                if self._check_raspotify_running():
                    logger.info("Successfully restarted raspotify service (verified after 5s)")
                    self._last_raspotify_restart = time.time()
                    self._device_id = None
                    self._last_device_check = 0
                    return True
                else:
                    logger.warning("raspotify restart command succeeded but service is not active after 5s")
                    return False
            else:
                error_msg = result.stderr or result.stdout or ''
                logger.warning(f"Failed to restart raspotify service: {error_msg}")
                if "Authentication" in error_msg or "permission" in error_msg.lower():
                    logger.error("Permission denied. Ensure polkit rule is installed: /etc/polkit-1/rules.d/50-rodrigo-radio.rules")
                return False
                
        except subprocess.TimeoutExpired:
            logger.warning("Timeout while restarting raspotify service")
            return False
        except FileNotFoundError:
            logger.debug("systemctl not found - cannot restart raspotify service")
            return False
        except Exception as e:
            logger.warning(f"Error restarting raspotify service: {e}")
            return False
    
    def _handle_rate_limit(self, error: Exception) -> bool:
        """
        Handle rate limit errors (429) with exponential backoff.
        
        Args:
            error: The exception that was raised
            
        Returns:
            True if rate limit was handled and we should retry, False otherwise
        """
        error_str = str(error).lower()
        is_rate_limit = (
            '429' in error_str or 
            'rate' in error_str and 'limit' in error_str or
            'too many requests' in error_str
        )
        
        if is_rate_limit:
            logger.warning(
                f"Rate limit hit. Waiting {self._rate_limit_backoff:.1f}s before retry. "
                f"Consider reducing API call frequency."
            )
            time.sleep(self._rate_limit_backoff)
            # Exponential backoff: double the delay, up to max
            self._rate_limit_backoff = min(
                self._rate_limit_backoff * 2,
                self._max_rate_limit_backoff
            )
            return True
        
        # Reset backoff on successful calls (will be reset when API call succeeds)
        return False
    
    def _throttle_api_call(self):
        """Ensure minimum time between API calls to avoid rate limiting."""
        current_time = time.time()
        time_since_last_call = current_time - self._last_api_call
        
        if time_since_last_call < self._min_api_call_interval:
            sleep_time = self._min_api_call_interval - time_since_last_call
            time.sleep(sleep_time)
        
        self._last_api_call = time.time()
    
    def _api_call_with_retry(self, func, *args, max_retries=3, **kwargs):
        """
        Execute an API call with rate limit handling and retries.
        
        Args:
            func: The API function to call
            *args: Positional arguments for the function
            max_retries: Maximum number of retries for rate limits
            **kwargs: Keyword arguments for the function
            
        Returns:
            The result of the API call
            
        Raises:
            The original exception if not a rate limit error or max retries exceeded
        """
        for attempt in range(max_retries + 1):
            try:
                self._throttle_api_call()
                result = func(*args, **kwargs)
                # Reset backoff on success
                self._rate_limit_backoff = 1.0
                return result
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 429 or self._handle_rate_limit(e):
                    if attempt < max_retries:
                        logger.debug(f"Rate limit on attempt {attempt + 1}/{max_retries + 1}, retrying...")
                        continue
                    else:
                        logger.error(f"Max retries ({max_retries}) reached for rate limit")
                        raise
                else:
                    # Not a rate limit error, re-raise
                    raise
            except Exception as e:
                if self._handle_rate_limit(e):
                    if attempt < max_retries:
                        logger.debug(f"Rate limit on attempt {attempt + 1}/{max_retries + 1}, retrying...")
                        continue
                    else:
                        logger.error(f"Max retries ({max_retries}) reached for rate limit")
                        raise
                else:
                    # Not a rate limit error, re-raise
                    raise
        
        # Should never reach here, but just in case
        raise Exception("Unexpected error in _api_call_with_retry")
    
    def _start_token_refresh_thread(self):
        """Start background thread for proactive token refresh."""
        if not self._auth_manager:
            return
        
        self._token_refresh_active = True
        
        def refresh_worker():
            """Background worker that periodically refreshes tokens to keep them alive."""
            while self._token_refresh_active:
                try:
                    # Wait for refresh interval (3 days)
                    time.sleep(self._token_refresh_interval)
                    
                    if not self._token_refresh_active:
                        break
                    
                    # Check if we need to refresh (every 3 days)
                    current_time = time.time()
                    if current_time - self._last_token_refresh >= self._token_refresh_interval:
                        logger.info("Proactively refreshing Spotify token to prevent expiration...")
                        try:
                            # Force a token refresh by getting a new access token
                            if self._auth_manager:
                                # Get cached token to check if refresh is needed
                                cached_token = self._auth_manager.get_cached_token()
                                if cached_token and 'refresh_token' in cached_token:
                                    # Force refresh by calling get_access_token with refresh
                                    # This will use the refresh token to get a new access token
                                    # and potentially update the refresh token
                                    try:
                                        # Make a simple API call which will trigger refresh if needed
                                        if self._spotify:
                                            self._spotify.current_user()
                                            self._last_token_refresh = time.time()
                                            logger.info("Successfully refreshed Spotify token")
                                        else:
                                            # Reinitialize if spotify client is None
                                            self._init_spotify()
                                            self._last_token_refresh = time.time()
                                            logger.info("Successfully refreshed Spotify token (after reinit)")
                                    except Exception as refresh_error:
                                        error_str = str(refresh_error).lower()
                                        if 'invalid_grant' in error_str or ('refresh_token' in error_str and ('expired' in error_str or 'invalid' in error_str)):
                                            logger.error(
                                                "Refresh token has expired during proactive refresh. "
                                                "You need to re-authenticate:\n"
                                                f"  Run: python3 {Path(__file__).parent.parent / 'scripts' / 'spotify_oauth_setup.py'}\n"
                                                "This will generate a new refresh token."
                                            )
                                            # Stop refresh thread since token is expired
                                            self._token_refresh_active = False
                                        else:
                                            logger.warning(f"Token refresh failed: {refresh_error}")
                                else:
                                    logger.warning("No refresh token available for proactive refresh")
                        except Exception as e:
                            logger.warning(f"Error during proactive token refresh: {e}")
                except Exception as e:
                    logger.error(f"Error in token refresh thread: {e}")
                    # Continue running despite errors
                    time.sleep(3600)  # Wait 1 hour before retrying on error
        
        self._token_refresh_thread = threading.Thread(target=refresh_worker, daemon=True)
        self._token_refresh_thread.start()
        logger.info("Started proactive token refresh thread (refreshes every 3 days)")
    
    def _stop_token_refresh_thread(self):
        """Stop the token refresh thread."""
        if self._token_refresh_active:
            self._token_refresh_active = False
            if self._token_refresh_thread and self._token_refresh_thread.is_alive():
                logger.info("Stopping token refresh thread")
    
    def _check_raspotify_running(self) -> bool:
        """Check if raspotify service is running."""
        # Try systemctl first (most reliable if available)
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', '--quiet', 'raspotify'],
                timeout=2,
                capture_output=True,
                check=False  # Don't raise on non-zero exit
            )
            if result.returncode == 0:
                logger.debug("raspotify is running (checked via systemctl)")
                return True
            else:
                logger.debug(f"systemctl check returned code {result.returncode}")
        except subprocess.TimeoutExpired:
            logger.debug("systemctl check timed out")
        except FileNotFoundError:
            logger.debug("systemctl not found, trying pgrep")
        except Exception as e:
            logger.debug(f"systemctl check failed: {e}")
        
        # Fallback: check if librespot process is running
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'librespot'],
                timeout=2,
                capture_output=True,
                check=False  # Don't raise on non-zero exit
            )
            if result.returncode == 0:
                logger.debug("raspotify is running (checked via pgrep)")
                return True
            else:
                logger.debug("pgrep did not find librespot process")
        except subprocess.TimeoutExpired:
            logger.debug("pgrep check timed out")
        except FileNotFoundError:
            logger.debug("pgrep not found")
        except Exception as e:
            logger.debug(f"pgrep check failed: {e}")
        
        logger.debug("raspotify check: not running")
        return False
    
    def _start_raspotify_service(self) -> bool:
        """
        Attempt to start the raspotify service.
        
        Returns:
            True if service was started successfully, False otherwise
        """
        # First check if it's already running
        is_running = self._check_raspotify_running()
        if is_running:
            logger.debug("raspotify is already running, no need to start it")
            return True
        
        # Double-check with a small delay in case of timing issues
        logger.debug("First check said not running, double-checking...")
        time.sleep(0.2)
        is_running = self._check_raspotify_running()
        if is_running:
            logger.info("raspotify is running (verified on second check)")
            return True
        
        logger.debug("Both checks confirmed raspotify is not running")
        
        try:
            # Use systemctl without sudo (requires polkit configuration)
            # This is necessary because the service runs with NoNewPrivileges=true
            # Polkit rule should be installed at /etc/polkit-1/rules.d/50-rodrigo-radio.rules
            logger.info("Attempting to start raspotify service...")
            
            result = subprocess.run(
                ['systemctl', 'start', 'raspotify'],
                timeout=10,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Give the service time to start and register with Spotify
                # Raspotify needs time to: start process, connect to Spotify, register as device
                logger.info("Waiting for raspotify to start and register with Spotify API...")
                for i in range(5):  # Wait up to 5 seconds, checking every second
                    time.sleep(1)
                    if self._check_raspotify_running():
                        logger.info(f"Successfully started raspotify service (verified after {i+1}s)")
                        return True
                # Final check
                if self._check_raspotify_running():
                    logger.info("Successfully started raspotify service (verified after 5s)")
                    return True
                else:
                    logger.warning("raspotify service start command succeeded but service is not active after 5s")
                    return False
            else:
                # Start command failed, but service might still be starting asynchronously
                # or might have been triggered to start by systemd
                error_msg = result.stderr or result.stdout or ''
                logger.warning(f"raspotify start command failed (code {result.returncode}): {error_msg}")
                if "Authentication" in error_msg or "permission" in error_msg.lower():
                    logger.error("Permission denied. Ensure polkit rule is installed: /etc/polkit-1/rules.d/50-rodrigo-radio.rules")
                logger.info("Checking if service starts anyway (may be starting asynchronously)...")
                
                # Wait and check if service becomes available anyway
                # Sometimes systemd starts services asynchronously or they're already starting
                for i in range(8):  # Wait up to 8 seconds, checking every second
                    time.sleep(1)
                    if self._check_raspotify_running():
                        logger.info(f"raspotify service is running (verified after {i+1}s, despite start command failure)")
                        return True
                
                # Final check
                if self._check_raspotify_running():
                    logger.info("raspotify service is running (verified after 8s, despite start command failure)")
                    return True
                
                # Check for specific errors that indicate we can't start it
                error_lower = error_msg.lower()
                if 'no new privileges' in error_lower or 'prevent sudo' in error_lower:
                    logger.error(
                        "Cannot start raspotify service: The rodrigo_radio service has 'NoNewPrivileges=true' "
                        "which prevents using sudo. Solutions:\n"
                        "1. Configure polkit (recommended): Install /etc/polkit-1/rules.d/50-rodrigo-radio.rules\n"
                        "2. Enable raspotify to start automatically: sudo systemctl enable raspotify\n"
                        "3. Start raspotify manually: sudo systemctl start raspotify\n"
                        "4. Remove 'NoNewPrivileges=true' from rodrigo_radio.service (less secure)"
                    )
                elif 'permission denied' in error_lower or 'access denied' in error_lower:
                    logger.error(
                        "Cannot start raspotify service: Permission denied. "
                        "The service requires root privileges. Solutions:\n"
                        "1. Configure polkit (recommended): Install /etc/polkit-1/rules.d/50-rodrigo-radio.rules\n"
                        "2. Enable raspotify to start automatically: sudo systemctl enable raspotify\n"
                        "3. Start raspotify manually: sudo systemctl start raspotify"
                    )
                return False
        except subprocess.TimeoutExpired:
            logger.warning("Timeout while starting raspotify service")
            return False
        except FileNotFoundError:
            logger.debug("sudo or systemctl not found - cannot start raspotify service")
            return False
        except Exception as e:
            # Check if it's a privilege-related error
            error_str = str(e).lower()
            if 'no new privileges' in error_str or 'privilege' in error_str:
                logger.debug(
                    f"Cannot start raspotify service due to privilege restrictions: {e}. "
                    "Service may need to be started manually."
                )
            else:
                logger.warning(f"Error starting raspotify service: {e}")
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
            
            # Check for manually configured device_id first
            config = getattr(self, '_config', None)
            if not config:
                config = self._load_config()
            configured_device_id = None
            if config and config.get('device_id'):
                device_id = config['device_id']
                logger.info(f"Using manually configured device_id: {device_id}")
                # Verify it's still available
                try:
                    devices = self._api_call_with_retry(self._spotify.devices)
                    device_list = devices.get('devices', [])
                    for device in device_list:
                        if device.get('id') == device_id:
                            is_active = device.get('is_active', False)
                            status = "ACTIVE" if is_active else "inactive"
                            logger.info(f"Verified configured device: {device.get('name')} ({device_id}) - {status}")
                            if not is_active:
                                logger.debug("Device is inactive - will need to transfer playback before starting")
                            return device_id
                    logger.warning(f"Configured device_id {device_id} not found in available devices - will search by name/keywords instead")
                    # Don't return None here - continue to search by name/keywords
                except Exception as e:
                    logger.warning(f"Could not verify configured device_id: {e}")
                    # Continue searching by name/keywords
            
            try:
                devices = self._api_call_with_retry(self._spotify.devices)
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 401:
                    logger.warning("Received 401 Unauthorized while finding device - attempting token refresh...")
                    try:
                        self._init_spotify()
                        devices = self._api_call_with_retry(self._spotify.devices)
                    except Exception as refresh_error:
                        logger.error(f"Failed to refresh token: {refresh_error}")
                        return None
                else:
                    raise
            
            device_list = devices.get('devices', [])
            
            # Check for manually configured device_name
            # Check this even if device_id was configured but not found (stale device_id)
            if config.get('device_name'):
                device_name_lower = config['device_name'].lower()
                for device in device_list:
                    if device.get('name', '').lower() == device_name_lower:
                        device_id = device.get('id')
                        if device_id:
                            logger.info(f"Found device by configured name '{config['device_name']}': {device_id}")
                            return device_id
            
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
                    
                    # On first attempt, try restarting raspotify to refresh connection
                    if self._device_activation_attempts == 1:
                        logger.info("Device not found - attempting to restart raspotify to refresh connection...")
                        if self._restart_raspotify_service():
                            # Wait a bit longer after restart for device to register
                            delay = 5.0
                            logger.info(f"Raspotify restarted, waiting {delay:.1f}s for device to register...")
                        else:
                            delay = self._activation_retry_delay
                    else:
                        delay = self._activation_retry_delay * (2 ** (self._device_activation_attempts - 2))
                    
                    logger.info(
                        f"Raspotify device not found in API (attempt {self._device_activation_attempts}/{self._max_activation_attempts}). "
                        f"Waiting {delay:.1f}s before retry..."
                    )
                    play_retry_beep()
                    time.sleep(delay)
                    # Retry finding the device
                    return self._find_raspotify_device(retry=True)
                else:
                    logger.warning(
                        f"Raspotify device not found after {self._max_activation_attempts} attempts. "
                        "Raspotify is running but not appearing in Spotify API. "
                        "This may require manual activation from Spotify app on first use."
                    )
            
            # If not found, log available devices at INFO level for debugging
            if device_list:
                logger.info("Raspotify device not found. Available devices in Spotify API:")
                for device in device_list:
                    device_name = device.get('name', 'Unknown')
                    device_id = device.get('id', 'Unknown')
                    device_type = device.get('type', 'Unknown')
                    is_active = device.get('is_active', False)
                    status = "ACTIVE" if is_active else "inactive"
                    logger.info(f"  - {device_name} ({device_type}) [{device_id}] - {status}")
                logger.info("Tip: If your device is listed above, you can configure it manually in spotify_api_config.json:")
                logger.info("  Add 'device_id': '<device_id>' or 'device_name': '<device_name>' to the config file")
            else:
                logger.warning("No devices found in Spotify API. The device needs to be activated first:")
                logger.warning("  1. Open Spotify app (mobile or desktop)")
                logger.warning("  2. Look for your Raspberry Pi device in the device list")
                logger.warning("  3. Connect to it (play something on it)")
                logger.warning("  4. Once connected, it will appear in the API")
            
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
        
        # Only check/start raspotify if we don't have a device yet
        # If we have a device_id, raspotify must be running (can't have device without it)
        if not self._device_id:
            raspotify_was_started = False
            # Check if raspotify is running
            if not self._check_raspotify_running():
                # Try to start the service automatically
                if self._start_raspotify_service():
                    raspotify_was_started = True
                    logger.info("raspotify service was started - will retry device lookup")
                else:
                    # Start command failed, but wait a bit to see if service starts anyway
                    logger.info("raspotify start command failed, but checking if service becomes available...")
                    # Wait up to 5 seconds to see if service starts asynchronously
                    for i in range(5):
                        time.sleep(1)
                        if self._check_raspotify_running():
                            logger.info(f"raspotify is running (verified after {i+1}s, despite start command failure)")
                            raspotify_was_started = True
                            break
                    
                    # Final check
                    if not self._check_raspotify_running():
                        raise BackendError(
                            "raspotify service is not running and could not be started automatically. "
                            "Start it manually with: sudo systemctl start raspotify\n"
                            "Or check if it's running with: systemctl status raspotify"
                        )
                    else:
                        logger.info("raspotify is running (verified after start attempt)")
            else:
                logger.debug("raspotify is running (checked before device lookup)")
            
            # If we just started raspotify, wait a bit for it to connect to Spotify and register
            # Then retry finding the device with retry enabled
            if raspotify_was_started:
                self._device_activation_attempts = 0
                logger.info("raspotify was just started - waiting for it to connect to Spotify and register as device...")
                # Give raspotify time to: start process, connect to Spotify servers, register as device
                # This can take 3-5 seconds on a slow connection
                time.sleep(3.0)
                logger.info("Retrying device lookup after raspotify startup...")
                self._device_id = self._find_raspotify_device(retry=True)
                self._last_device_check = current_time
            
            # If still no device, check for MPRIS fallback
            if not self._device_id:
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
    
    def _ensure_device_active(self) -> bool:
        """
        Ensure the device is active (selected in Spotify).
        If inactive, transfer playback to it.
        
        Returns:
            True if device is active or was successfully activated, False otherwise
        """
        if not self._device_id or not self._spotify:
            return False
        
        try:
            # Get current device list
            devices = self._api_call_with_retry(self._spotify.devices)
            device_list = devices.get('devices', [])
            
            # Find our device and check if it's active
            for device in device_list:
                if device.get('id') == self._device_id:
                    is_active = device.get('is_active', False)
                    if is_active:
                        logger.debug(f"Device {self._device_id} is already active")
                        return True
                    else:
                        # Device is inactive, transfer playback to it
                        logger.info(f"Device {self._device_id} is inactive, transferring playback to it...")
                        try:
                            self._api_call_with_retry(
                                self._spotify.transfer_playback,
                                device_id=self._device_id,
                                force_play=False
                            )
                            # Give it a moment to transfer
                            time.sleep(0.5)
                            logger.info("Successfully transferred playback to device")
                            return True
                        except spotipy.exceptions.SpotifyException as e:
                            if e.http_status == 404:
                                logger.warning("Device not found when trying to transfer playback - device may have disconnected")
                                # Try restarting raspotify to refresh connection
                                logger.info("Attempting to restart raspotify to resolve device connection issue...")
                                if self._restart_raspotify_service():
                                    # Wait for device to reappear
                                    time.sleep(3.0)
                                    # Force device refresh
                                    self._device_id = None
                                    self._last_device_check = 0
                                else:
                                    # Force device refresh anyway
                                    self._device_id = None
                                    self._last_device_check = 0
                                return False
                            elif e.http_status == 429:
                                logger.warning("Rate limit hit while transferring playback - attempting to restart raspotify...")
                                # Try restarting raspotify when hitting rate limits during device activation
                                if self._restart_raspotify_service():
                                    # Wait for device to reappear after restart
                                    time.sleep(3.0)
                                    # Force device refresh
                                    self._device_id = None
                                    self._last_device_check = 0
                                return False
                            else:
                                logger.warning(f"Failed to transfer playback to device: {e}")
                                return False
            
            # Device not found in list - might have disconnected
            logger.warning(f"Device {self._device_id} not found in device list - device may have disconnected")
            # Try restarting raspotify to refresh connection
            logger.info("Attempting to restart raspotify to resolve device connection issue...")
            if self._restart_raspotify_service():
                # Wait for device to reappear
                time.sleep(3.0)
            self._device_id = None
            self._last_device_check = 0
            return False
            
        except Exception as e:
            logger.warning(f"Error checking/activating device: {e}")
            return False
    
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
                    result = self._api_call_with_retry(
                        self._spotify.playlist_tracks,
                        uri_id,
                        limit=1
                    )
                    total = result.get('total', 0)
                    return total if total > 0 else None
                except Exception as e:
                    logger.debug(f"Could not get playlist track count: {e}")
                    return None
            elif uri_type == 'album':
                # Get album tracks count
                try:
                    album = self._api_call_with_retry(self._spotify.album, uri_id)
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
            if not self._spotify:
                raise BackendError("Spotify client not initialized")
            
            # Get URI to play
            playlist_id = kwargs.get('playlist_id') or source_id
            uri = self._normalize_uri(playlist_id)
            self._current_playlist_id = uri
            
            # Ensure we have a device (with automatic activation retries)
            # This will also check for raspotify if needed
            self._ensure_device(retry=True)
            
            # If we have a device ID, raspotify is likely running
            # Only check/start if we don't have a device yet
            if not self._device_id:
                # Check if raspotify is running
                if not self._check_raspotify_running():
                    # Try to start the service automatically
                    if not self._start_raspotify_service():
                        # Double-check - it might have been running but our check failed
                        # or it might have started in the meantime
                        time.sleep(0.5)
                        if self._check_raspotify_running():
                            logger.info("raspotify is running (verified after start attempt)")
                        else:
                            raise BackendError(
                                "raspotify service is not running and could not be started automatically. "
                                "Start it manually with: sudo systemctl start raspotify\n"
                                "Or check if it's running with: systemctl status raspotify"
                            )
            
            # Ensure device is active (selected in Spotify) before trying to play
            # Inactive devices will return 404 when trying to play
            if self._device_id:
                if not self._ensure_device_active():
                    # Device activation failed, try to refresh device
                    logger.warning("Device activation failed, refreshing device...")
                    # Try restarting raspotify if activation failed (could be connection issue)
                    logger.info("Attempting to restart raspotify to resolve device activation issue...")
                    if self._restart_raspotify_service():
                        time.sleep(3.0)
                    self._device_id = None
                    self._last_device_check = 0
                    self._ensure_device(retry=True)
                    if self._device_id:
                        self._ensure_device_active()
            
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
                    self._api_call_with_retry(
                        self._spotify.start_playback,
                        device_id=self._device_id,
                        context_uri=uri,
                        offset={'position': random_offset}
                    )
                    logger.info(f"Started playback from random position: {uri}")
                else:
                    # Start from beginning (single track or couldn't get count)
                    self._api_call_with_retry(
                        self._spotify.start_playback,
                        device_id=self._device_id,
                        context_uri=uri
                    )
                    logger.info(f"Started playback: {uri}")
                
                # Enable shuffle mode (with small delay to avoid rate limits)
                time.sleep(0.3)
                try:
                    self._api_call_with_retry(
                        self._spotify.shuffle,
                        state=True,
                        device_id=self._device_id
                    )
                    logger.info("Shuffle mode enabled")
                except Exception as shuffle_error:
                    logger.warning(f"Could not enable shuffle mode: {shuffle_error}")
                    # Continue anyway - playback started successfully
                
                self.set_playing_state(True)
                self._is_paused = False
                
                # Try to get current track info
                time.sleep(1)  # Wait a bit for playback to start
                self._update_current_item()
                
                # Start monitoring thread to detect when playlist ends
                self._start_monitoring()
                
                return True
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 401:
                    # Token expired or invalid - try to refresh
                    logger.warning("Received 401 Unauthorized - token may be expired, attempting refresh...")
                    try:
                        # Reinitialize Spotify client to trigger token refresh
                        self._init_spotify()
                        self._last_token_refresh = time.time()
                        
                        # Get track count and pick a random starting position for shuffle
                        track_count = self._get_track_count(uri)
                        random_offset = None
                        if track_count and track_count > 1:
                            random_offset = random.randint(0, track_count - 1)
                            logger.info(f"Starting playback from random track {random_offset + 1} of {track_count} (after refresh)")
                        
                        # Retry playback
                        if random_offset is not None:
                            self._api_call_with_retry(
                                self._spotify.start_playback,
                                device_id=self._device_id,
                                context_uri=uri,
                                offset={'position': random_offset}
                            )
                            logger.info(f"Started playback from random position after token refresh: {uri}")
                        else:
                            self._api_call_with_retry(
                                self._spotify.start_playback,
                                device_id=self._device_id,
                                context_uri=uri
                            )
                            logger.info(f"Started playback after token refresh: {uri}")
                        
                        # Enable shuffle mode (with small delay to avoid rate limits)
                        time.sleep(0.3)
                        try:
                            self._api_call_with_retry(
                                self._spotify.shuffle,
                                state=True,
                                device_id=self._device_id
                            )
                            logger.info("Shuffle mode enabled after token refresh")
                        except Exception as shuffle_error:
                            logger.warning(f"Could not enable shuffle mode: {shuffle_error}")
                        
                        self.set_playing_state(True)
                        self._is_paused = False
                        time.sleep(1)
                        self._update_current_item()
                        
                        # Start monitoring thread to detect when playlist ends
                        self._start_monitoring()
                        
                        return True
                    except Exception as refresh_error:
                        error_str = str(refresh_error).lower()
                        # Check if refresh token has expired
                        if 'invalid_grant' in error_str or ('refresh_token' in error_str and ('expired' in error_str or 'invalid' in error_str)):
                            play_auth_error_beep()
                            raise BackendError(
                                "Spotify refresh token has expired. You need to re-authenticate:\n"
                                f"  Run: python3 {Path(__file__).parent.parent / 'scripts' / 'spotify_oauth_setup.py'}\n"
                                "This will generate a new refresh token. Refresh tokens expire after ~60 days of inactivity."
                            )
                        else:
                            play_auth_error_beep()
                            raise BackendError(
                                f"Authentication failed and token refresh unsuccessful: {refresh_error}. "
                                "You may need to run spotify_oauth_setup.py again to re-authenticate."
                            )
                elif e.http_status == 404:
                    # 404 could mean device not found OR playlist not found
                    # Check if it's a device issue first
                    error_msg = str(e).lower()
                    if 'device' in error_msg or 'not found' in error_msg:
                        logger.warning("Received 404 - device may not be active. Attempting to activate device...")
                        # Try restarting raspotify first if device activation fails
                        device_activated = self._ensure_device_active()
                        if not device_activated:
                            logger.info("Device activation failed - attempting to restart raspotify...")
                            if self._restart_raspotify_service():
                                time.sleep(3.0)
                                # Reset device and try again
                                self._device_id = None
                                self._last_device_check = 0
                                self._ensure_device(retry=True)
                                device_activated = self._ensure_device_active()
                        
                        # Try to activate device and retry
                        if device_activated:
                            # Recalculate track count and offset for retry
                            track_count = self._get_track_count(uri)
                            random_offset = None
                            if track_count and track_count > 1:
                                random_offset = random.randint(0, track_count - 1)
                                logger.info(f"Starting playback from random track {random_offset + 1} of {track_count} (after device activation)")
                            
                            # Retry playback once
                            try:
                                if random_offset is not None:
                                    self._api_call_with_retry(
                                        self._spotify.start_playback,
                                        device_id=self._device_id,
                                        context_uri=uri,
                                        offset={'position': random_offset}
                                    )
                                    logger.info(f"Started playback after device activation: {uri}")
                                else:
                                    self._api_call_with_retry(
                                        self._spotify.start_playback,
                                        device_id=self._device_id,
                                        context_uri=uri
                                    )
                                    logger.info(f"Started playback after device activation: {uri}")
                                
                                # Enable shuffle mode (with small delay to avoid rate limits)
                                time.sleep(0.3)
                                try:
                                    self._api_call_with_retry(
                                        self._spotify.shuffle,
                                        state=True,
                                        device_id=self._device_id
                                    )
                                    logger.info("Shuffle mode enabled after device activation")
                                except Exception as shuffle_error:
                                    logger.warning(f"Could not enable shuffle mode: {shuffle_error}")
                                
                                self.set_playing_state(True)
                                self._is_paused = False
                                time.sleep(1)
                                self._update_current_item()
                                self._start_monitoring()
                                return True
                            except Exception as retry_error:
                                logger.error(f"Playback still failed after device activation: {retry_error}")
                                play_not_found_beep()
                                raise BackendError(f"Failed to start playback: {retry_error}")
                        else:
                            # Last resort: try restarting raspotify one more time
                            logger.warning("Device activation still failed after restart - this may require manual activation from Spotify app")
                            play_not_found_beep()
                            raise BackendError(f"Device not found and could not be activated. Try restarting raspotify manually: sudo systemctl restart raspotify")
                    else:
                        play_not_found_beep()
                        raise BackendError(f"Playlist/album/track not found: {uri}")
                elif e.http_status == 403:
                    raise BackendError("Permission denied. Make sure your Spotify account has Premium.")
                elif e.http_status == 429:
                    # Rate limit error - try restarting raspotify first, then retry
                    logger.warning("Rate limit hit during playback. Attempting to restart raspotify...")
                    play_retry_beep()
                    # Try restarting raspotify to reset connection state
                    if self._restart_raspotify_service():
                        logger.info("Raspotify restarted, waiting before retry...")
                        time.sleep(5.0)  # Wait longer after restart
                        # Reset device to force re-discovery
                        self._device_id = None
                        self._last_device_check = 0
                    else:
                        # If restart failed, just wait with backoff
                        time.sleep(self._rate_limit_backoff)
                        # Exponential backoff
                        self._rate_limit_backoff = min(
                            self._rate_limit_backoff * 2,
                            self._max_rate_limit_backoff
                        )
                    # Retry the entire play operation once
                    logger.info("Retrying playback after rate limit handling...")
                    return self.play(source_id, **kwargs)
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
                    self._api_call_with_retry(
                        self._spotify.pause_playback,
                        device_id=self._device_id
                    )
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
                            self._api_call_with_retry(
                                self._spotify.pause_playback,
                                device_id=self._device_id
                            )
                            self._is_paused = True
                            logger.info("Paused Spotify playback (Web API) after token refresh")
                            return True
                        except Exception:
                            logger.debug("Web API pause failed after token refresh, trying MPRIS fallback")
                    elif e.http_status == 429:
                        logger.warning("Rate limit hit during pause, trying MPRIS fallback")
                    else:
                        logger.debug(f"Web API pause failed: {e}, trying MPRIS fallback")
                except Exception as e:
                    if self._handle_rate_limit(e):
                        logger.warning("Rate limit hit during pause, trying MPRIS fallback")
                    else:
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
                    self._api_call_with_retry(
                        self._spotify.start_playback,
                        device_id=self._device_id
                    )
                    self._is_paused = False
                    self.set_playing_state(True)
                    logger.info("Resumed Spotify playback (Web API)")
                    return True
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 401:
                        logger.debug("Received 401 Unauthorized during resume - attempting token refresh...")
                        try:
                            self._init_spotify()
                            self._api_call_with_retry(
                                self._spotify.start_playback,
                                device_id=self._device_id
                            )
                            self._is_paused = False
                            self.set_playing_state(True)
                            logger.info("Resumed Spotify playback (Web API) after token refresh")
                            return True
                        except Exception:
                            logger.debug("Web API resume failed after token refresh, trying MPRIS fallback")
                    elif e.http_status == 429:
                        logger.warning("Rate limit hit during resume, trying MPRIS fallback")
                    else:
                        logger.debug(f"Web API resume failed: {e}, trying MPRIS fallback")
                except Exception as e:
                    if self._handle_rate_limit(e):
                        logger.warning("Rate limit hit during resume, trying MPRIS fallback")
                    else:
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
                    self._api_call_with_retry(
                        self._spotify.pause_playback,
                        device_id=self._device_id
                    )
                    logger.info("Paused Spotify playback (stop)")
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 401:
                        logger.debug("Received 401 Unauthorized during stop pause - attempting token refresh...")
                        try:
                            self._init_spotify()
                            self._api_call_with_retry(
                                self._spotify.pause_playback,
                                device_id=self._device_id
                            )
                            logger.info("Paused Spotify playback (stop) after token refresh")
                        except Exception:
                            logger.debug("Could not pause during stop after token refresh")
                    elif e.http_status == 429:
                        logger.warning("Rate limit hit during stop - continuing anyway")
                    else:
                        raise
                
                # Wait a moment and verify it's actually stopped
                time.sleep(0.2)
                
                # Check if it's still playing and force stop if needed
                try:
                    playback = self._api_call_with_retry(self._spotify.current_playback, max_retries=1)
                    if playback and playback.get('is_playing', False):
                        # Still playing, try to pause again more aggressively
                        logger.warning("Spotify still playing after pause, forcing stop...")
                        self._api_call_with_retry(
                            self._spotify.pause_playback,
                            device_id=self._device_id
                        )
                        time.sleep(0.2)
                        
                        # Check one more time
                        playback = self._api_call_with_retry(self._spotify.current_playback, max_retries=1)
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
                    elif e.http_status == 429:
                        logger.debug("Rate limit hit while verifying stop - continuing anyway")
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
            
            # Stop monitoring thread
            self._stop_monitoring()
            
            # Stop token refresh thread
            self._stop_token_refresh_thread()
            
            # Clear callback to avoid stale callbacks
            self.set_on_playback_ended_callback(None)
            
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
                    self._api_call_with_retry(
                        self._spotify.next_track,
                        device_id=self._device_id
                    )
                    logger.info("Skipped to next track (Web API)")
                    time.sleep(0.5)
                    self._update_current_item()
                    return True
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 401:
                        logger.debug("Received 401 Unauthorized during next - attempting token refresh...")
                        try:
                            self._init_spotify()
                            self._api_call_with_retry(
                                self._spotify.next_track,
                                device_id=self._device_id
                            )
                            logger.info("Skipped to next track (Web API) after token refresh")
                            time.sleep(0.5)
                            self._update_current_item()
                            return True
                        except Exception:
                            logger.debug("Web API next failed after token refresh, trying MPRIS fallback")
                    elif e.http_status == 429:
                        logger.warning("Rate limit hit during next, trying MPRIS fallback")
                    else:
                        logger.debug(f"Web API next failed: {e}, trying MPRIS fallback")
                except Exception as e:
                    if self._handle_rate_limit(e):
                        logger.warning("Rate limit hit during next, trying MPRIS fallback")
                    else:
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
                    self._api_call_with_retry(
                        self._spotify.previous_track,
                        device_id=self._device_id
                    )
                    logger.info("Went to previous track (Web API)")
                    time.sleep(0.5)
                    self._update_current_item()
                    return True
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 401:
                        logger.debug("Received 401 Unauthorized during previous - attempting token refresh...")
                        try:
                            self._init_spotify()
                            self._api_call_with_retry(
                                self._spotify.previous_track,
                                device_id=self._device_id
                            )
                            logger.info("Went to previous track (Web API) after token refresh")
                            time.sleep(0.5)
                            self._update_current_item()
                            return True
                        except Exception:
                            logger.debug("Web API previous failed after token refresh, trying MPRIS fallback")
                    elif e.http_status == 429:
                        logger.warning("Rate limit hit during previous, trying MPRIS fallback")
                    else:
                        logger.debug(f"Web API previous failed: {e}, trying MPRIS fallback")
                except Exception as e:
                    if self._handle_rate_limit(e):
                        logger.warning("Rate limit hit during previous, trying MPRIS fallback")
                    else:
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
                playback = self._api_call_with_retry(self._spotify.current_playback, max_retries=2)
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 401:
                    logger.debug("Received 401 Unauthorized while updating current item - attempting token refresh...")
                    try:
                        self._init_spotify()
                        playback = self._api_call_with_retry(self._spotify.current_playback, max_retries=2)
                    except Exception:
                        # If refresh fails, just skip updating current item
                        return
                elif e.http_status == 429:
                    # Rate limit - just skip updating this time
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
    
    def get_playback_info(self) -> Optional[dict]:
        """Get current playback position and duration from Spotify API."""
        try:
            if not self._spotify:
                return None
            
            try:
                playback = self._api_call_with_retry(self._spotify.current_playback, max_retries=2)
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 401:
                    logger.debug("Received 401 Unauthorized while getting playback info - attempting token refresh...")
                    try:
                        self._init_spotify()
                        playback = self._api_call_with_retry(self._spotify.current_playback, max_retries=2)
                    except Exception:
                        return None
                elif e.http_status == 429:
                    # Rate limit - return None to skip this update
                    return None
                else:
                    return None
            except Exception:
                return None
            
            if not playback:
                return None
            
            # Update current item if available
            item = playback.get('item')
            if item:
                title = item.get('name', 'Unknown')
                artists = [artist['name'] for artist in item.get('artists', [])]
                artist_str = ', '.join(artists) if artists else 'Unknown'
                self.set_current_item(f"{artist_str} - {title}")
            else:
                # No item means nothing is loaded/playing
                self.set_current_item(None)
                return None
            
            progress_ms = playback.get('progress_ms')
            duration_ms = item.get('duration_ms')
            
            # Validate data - progress_ms should never exceed duration_ms
            if progress_ms is not None and duration_ms is not None:
                if progress_ms > duration_ms:
                    logger.warning(
                        f"Invalid playback data: progress_ms ({progress_ms}) > duration_ms ({duration_ms}). "
                        "This may indicate stale or incorrect API data."
                    )
                    # Cap progress_ms to duration_ms for safety
                    progress_ms = min(progress_ms, duration_ms)
            
            # If we have an item but no progress/duration info, still return item info
            # (though position/duration won't be available)
            if progress_ms is None and duration_ms is None:
                # Return empty dict to indicate we have item info but no position/duration
                return {}
            
            info = {}
            
            if progress_ms is not None:
                info['position_ms'] = progress_ms
                info['position'] = self._format_time(progress_ms)
            
            if duration_ms is not None:
                info['duration_ms'] = duration_ms
                info['duration'] = self._format_time(duration_ms)
            
            # Calculate progress percentage if both are available
            if progress_ms is not None and duration_ms is not None and duration_ms > 0:
                info['progress'] = min(100, max(0, (progress_ms / duration_ms) * 100))
            
            return info if info else None
            
        except Exception as e:
            logger.debug(f"Error getting playback info: {e}")
            return None
    
    def _format_time(self, ms: int) -> str:
        """Format milliseconds to MM:SS or HH:MM:SS."""
        total_seconds = ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
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
                    playback = self._api_call_with_retry(self._spotify.current_playback, max_retries=2)
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
                            playback = self._api_call_with_retry(self._spotify.current_playback, max_retries=2)
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
                    elif e.http_status == 429:
                        # Rate limit - fall through to MPRIS or internal state
                        pass
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
    
    def _start_monitoring(self):
        """Start monitoring thread to detect when playlist ends."""
        if self._monitoring_active:
            return  # Already monitoring
        
        self._monitoring_active = True
        self._was_playing = True
        # Reset track change detection so we don't get a false change on first check
        self._last_track_item_id = None
        
        def monitor():
            self._monitor_playback()
        
        self._monitoring_thread = threading.Thread(target=monitor, daemon=True)
        self._monitoring_thread.start()
        logger.info("Started Spotify playback monitoring thread")
    
    def _stop_monitoring(self):
        """Stop monitoring thread."""
        if not self._monitoring_active:
            return
        
        self._monitoring_active = False
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            # Thread will exit on next check
            logger.info("Stopping Spotify playback monitoring thread")
    
    def _monitor_playback(self):
        """
        Background thread to monitor Spotify playback and detect when playlist ends.
        When playlist ends naturally (not paused), notify callback to cycle to next source.
        Also updates current item and detects track changes.
        """
        consecutive_stopped_checks = 0
        required_stopped_checks = 3  # Require 3 consecutive checks to confirm playlist ended
        track_update_interval = 3.0  # Update track info every 3 seconds
        last_track_update = 0
        
        while self._monitoring_active:
            try:
                # Check if we have a playlist to monitor
                if not self._current_playlist_id:
                    time.sleep(2.0)
                    continue
                
                current_time = time.time()
                
                # Periodically update current item to keep it fresh
                if current_time - last_track_update >= track_update_interval:
                    try:
                        # Use get_playback_info() which updates current item and gets fresh data
                        playback_info = self.get_playback_info()
                        
                        if playback_info is not None:
                            # get_playback_info() already updated self._current_item
                            # Now check if the track actually changed by comparing Spotify track IDs
                            if self._spotify:
                                try:
                                    playback = self._api_call_with_retry(self._spotify.current_playback, max_retries=1)
                                    if playback and playback.get('item'):
                                        current_track_id = playback['item'].get('id')
                                        
                                        # Detect track change
                                        if current_track_id and current_track_id != self._last_track_item_id:
                                            if self._last_track_item_id is not None:
                                                # Track changed (not the first time we're seeing it)
                                                new_item_name = self._current_item
                                                if new_item_name:
                                                    logger.debug(f"Track changed to: {new_item_name}")
                                                    self._notify_track_changed(new_item_name)
                                            
                                            self._last_track_item_id = current_track_id
                                        elif not current_track_id:
                                            # No track ID available, reset
                                            self._last_track_item_id = None
                                except Exception as e:
                                    # If we can't get track ID, that's okay - just continue
                                    logger.debug(f"Could not get track ID for change detection: {e}")
                        
                        last_track_update = current_time
                    except Exception as e:
                        logger.debug(f"Error updating current item in monitoring thread: {e}")
                        # Continue monitoring despite errors
                
                # Check current playback state
                currently_playing = self.is_playing()
                
                if currently_playing:
                    # Reset counter if playing
                    consecutive_stopped_checks = 0
                    self._was_playing = True
                elif self._was_playing and not self._is_paused:
                    # Was playing but now stopped (and not paused) - playlist might have ended
                    consecutive_stopped_checks += 1
                    
                    if consecutive_stopped_checks >= required_stopped_checks:
                        # Playlist has ended naturally
                        logger.info("Spotify playlist ended - notifying callback to cycle to next source")
                        self._was_playing = False
                        self._notify_playback_ended()
                        # Stop monitoring since we've notified
                        self._monitoring_active = False
                        break
                else:
                    # Not playing and was already stopped (or paused) - reset
                    consecutive_stopped_checks = 0
                    self._was_playing = False
                
                # Sleep before next check
                time.sleep(2.0)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"Error in Spotify playback monitoring thread: {e}")
                # Continue monitoring despite errors
                time.sleep(2.0)
