#!/usr/bin/env python3
"""
One-time OAuth setup script for Spotify Web API.
This script helps you get the refresh token needed for programmatic control.

Steps:
1. Go to https://developer.spotify.com/dashboard
2. Create a new app
3. Add redirect URI: http://127.0.0.1:8888/callback
4. Get Client ID and Client Secret
5. Run this script and follow the prompts
"""
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import os
from pathlib import Path

# Configuration
SCOPE = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
# Try project directory first, then fall back to home directory for backwards compatibility
_PROJECT_DIR = Path(__file__).parent.parent.absolute()
if (_PROJECT_DIR / "config" / "spotify_api_config.json").exists() or (_PROJECT_DIR / "config" / "spotify_api_config.json.example").exists():
    CONFIG_FILE = _PROJECT_DIR / "config" / "spotify_api_config.json"
else:
    CONFIG_FILE = Path.home() / "music-player" / "spotify_api_config.json"

def get_credentials():
    """Get credentials from user input."""
    print("=" * 60)
    print("Spotify Web API OAuth Setup")
    print("=" * 60)
    print("\n1. Go to https://developer.spotify.com/dashboard")
    print("2. Click 'Create app'")
    print("3. Fill in app details (name, description)")
    print("4. Add redirect URI: http://127.0.0.1:8888/callback")
    print("5. Save and copy your Client ID and Client Secret")
    print("\n" + "=" * 60 + "\n")
    
    client_id = input("Enter your Client ID: ").strip()
    client_secret = input("Enter your Client Secret: ").strip()
    
    return client_id, client_secret

def save_config(client_id, client_secret, refresh_token):
    """Save configuration to file."""
    config = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE
    }
    
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    
    # Set restrictive permissions
    os.chmod(CONFIG_FILE, 0o600)
    print(f"\n✓ Configuration saved to {CONFIG_FILE}")
    print("✓ File permissions set to 600 (owner read/write only)")

def main():
    """Main OAuth flow."""
    client_id, client_secret = get_credentials()
    
    print("\nOpening browser for authorization...")
    print("If browser doesn't open, visit the URL shown below.\n")
    
    # Create OAuth manager
    # Cache path should be in project root, not config directory
    cache_path = _PROJECT_DIR / ".spotify_cache" if _PROJECT_DIR.exists() else CONFIG_FILE.parent / ".spotify_cache"
    sp_oauth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_path=str(cache_path)
    )
    
    # Get authorization URL
    auth_url = sp_oauth.get_authorize_url()
    print(f"Authorization URL: {auth_url}\n")
    
    # Try to open browser
    try:
        import webbrowser
        webbrowser.open(auth_url)
    except:
        print("Could not open browser automatically. Please visit the URL above.")
    
    # Get authorization code from user
    print("\nAfter authorizing, you'll be redirected to a page.")
    print("Copy the ENTIRE URL from your browser's address bar and paste it here:")
    response = input("Paste redirect URL here: ").strip()
    
    # Extract code from URL
    code = sp_oauth.parse_response_code(response)
    
    if not code:
        print("Error: Could not extract authorization code from URL")
        return False
    
    # Get access token and refresh token
    print("\nExchanging authorization code for tokens...")
    token_info = sp_oauth.get_access_token(code)
    
    # get_access_token returns a dict with token info
    if isinstance(token_info, dict):
        if 'refresh_token' not in token_info:
            print("Error: Failed to get refresh token")
            return False
        refresh_token = token_info['refresh_token']
    else:
        # If it returns just the token string, get cached token info
        cached_token = sp_oauth.get_cached_token()
        if not cached_token or 'refresh_token' not in cached_token:
            print("Error: Failed to get refresh token")
            return False
        refresh_token = cached_token['refresh_token']
    
    # Save configuration
    save_config(client_id, client_secret, refresh_token)
    
    # Test the connection
    print("\nTesting connection...")
    try:
        sp = spotipy.Spotify(auth_manager=sp_oauth)
        user = sp.current_user()
        print(f"✓ Successfully authenticated as: {user['display_name']} ({user['id']})")
        print("\n✓ OAuth setup complete! You can now use the Spotify backend.")
        return True
    except Exception as e:
        print(f"Error testing connection: {e}")
        return False

if __name__ == '__main__':
    try:
        success = main()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        exit(1)

