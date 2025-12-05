#!/usr/bin/env python3
"""
Utility script to proactively refresh Spotify tokens to prevent expiration.

This script can be run manually or via cron to keep Spotify tokens alive.
Refresh tokens expire after ~60 days of inactivity, so running this every 3 days
provides a good safety margin and ensures tokens stay valid.

Usage:
    python3 scripts/refresh_spotify_token.py

For cron (every 3 days at 2 AM - recommended for extra safety):
    0 2 */3 * * /usr/bin/python3 /home/skayflakes/rodrigo_radio/scripts/refresh_spotify_token.py >> /var/log/spotify_token_refresh.log 2>&1

Alternative cron (weekly on Sundays at 2 AM):
    0 2 * * 0 /usr/bin/python3 /home/skayflakes/rodrigo_radio/scripts/refresh_spotify_token.py >> /var/log/spotify_token_refresh.log 2>&1
"""
import json
import sys
import logging
from pathlib import Path

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False
    print("Error: spotipy is not installed. Install it with: pip3 install --user --break-system-packages spotipy")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration paths
_PROJECT_DIR = Path(__file__).parent.parent.absolute()
if (_PROJECT_DIR / "config" / "spotify_api_config.json").exists():
    CONFIG_FILE = _PROJECT_DIR / "config" / "spotify_api_config.json"
    CACHE_DIR = _PROJECT_DIR
else:
    CONFIG_FILE = Path.home() / "rodrigo_radio" / "spotify_api_config.json"
    CACHE_DIR = Path.home() / "rodrigo_radio"

def load_config():
    """Load Spotify API configuration."""
    if not CONFIG_FILE.exists():
        logger.error(f"Config file not found: {CONFIG_FILE}")
        logger.error("Run spotify_oauth_setup.py first to set up authentication.")
        return None
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        
        required_keys = ['client_id', 'client_secret', 'refresh_token']
        missing = [key for key in required_keys if key not in config]
        if missing:
            logger.error(f"Missing required config keys: {missing}")
            return None
        
        return config
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return None

def refresh_token():
    """Refresh Spotify token."""
    config = load_config()
    if not config:
        return False
    
    cache_path = CACHE_DIR / ".spotify_cache"
    
    try:
        # Create OAuth manager
        auth_manager = SpotifyOAuth(
            client_id=config['client_id'],
            client_secret=config['client_secret'],
            redirect_uri=config.get('redirect_uri', 'http://127.0.0.1:8888/callback'),
            scope=config.get('scope', 'user-read-playback-state user-modify-playback-state user-read-currently-playing'),
            cache_path=str(cache_path)
        )
        
        # Ensure cache has refresh token
        cached_token = auth_manager.get_cached_token()
        if not cached_token or 'refresh_token' not in cached_token:
            if 'refresh_token' in config:
                token_data = {
                    'refresh_token': config['refresh_token'],
                    'scope': config.get('scope', 'user-read-playback-state user-modify-playback-state user-read-currently-playing')
                }
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_path, 'w') as f:
                    json.dump(token_data, f)
                logger.info("Initialized cache file with refresh token from config")
            else:
                logger.error("No refresh token found in config or cache")
                return False
        elif cached_token.get('refresh_token') != config.get('refresh_token'):
            # Update cache with config refresh token
            cached_token['refresh_token'] = config['refresh_token']
            with open(cache_path, 'w') as f:
                json.dump(cached_token, f)
            logger.info("Updated cache file with refresh token from config")
        
        # Create Spotify client and make an API call to trigger token refresh
        logger.info("Refreshing Spotify token...")
        spotify = spotipy.Spotify(auth_manager=auth_manager)
        
        # Make a simple API call which will trigger refresh if needed
        user = spotify.current_user()
        logger.info(f"✓ Token refreshed successfully. Authenticated as: {user.get('display_name', 'Unknown')} ({user.get('id', 'Unknown')})")
        
        # Check if refresh token was updated in cache
        updated_token = auth_manager.get_cached_token()
        if updated_token and updated_token.get('refresh_token') != config.get('refresh_token'):
            # Refresh token was updated, save it back to config
            logger.info("Refresh token was updated, saving to config...")
            config['refresh_token'] = updated_token['refresh_token']
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info("✓ Updated refresh token in config file")
        
        return True
        
    except Exception as e:
        error_str = str(e).lower()
        if 'invalid_grant' in error_str or ('refresh_token' in error_str and ('expired' in error_str or 'invalid' in error_str)):
            logger.error(
                "✗ Refresh token has expired. You need to re-authenticate:\n"
                f"  Run: python3 {_PROJECT_DIR / 'scripts' / 'spotify_oauth_setup.py'}\n"
                "This will generate a new refresh token. Refresh tokens expire after ~60 days of inactivity."
            )
        else:
            logger.error(f"✗ Failed to refresh token: {e}")
        return False

def main():
    """Main function."""
    logger.info("=" * 60)
    logger.info("Spotify Token Refresh Utility")
    logger.info("=" * 60)
    
    success = refresh_token()
    
    if success:
        logger.info("=" * 60)
        logger.info("✓ Token refresh completed successfully")
        logger.info("=" * 60)
        return 0
    else:
        logger.error("=" * 60)
        logger.error("✗ Token refresh failed")
        logger.error("=" * 60)
        return 1

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)

