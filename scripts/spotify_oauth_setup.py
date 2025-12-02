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

The script will automatically open your browser and capture the authorization callback.
No need to manually copy/paste URLs!
"""
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import os
from pathlib import Path
import http.server
import socketserver
import threading
import urllib.parse
import webbrowser
import time

# Configuration
SCOPE = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
# Try project directory first, then fall back to home directory for backwards compatibility
_PROJECT_DIR = Path(__file__).parent.parent.absolute()
if (_PROJECT_DIR / "config" / "spotify_api_config.json").exists() or (_PROJECT_DIR / "config" / "spotify_api_config.json.example").exists():
    CONFIG_FILE = _PROJECT_DIR / "config" / "spotify_api_config.json"
else:
    CONFIG_FILE = Path.home() / "rodrigo_radio" / "spotify_api_config.json"

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

def create_callback_handler(callback_data):
    """
    Create a callback handler class that uses the provided callback_data.
    
    Args:
        callback_data: Dictionary to store callback information
    
    Returns:
        Handler class
    """
    class CallbackHandler(http.server.SimpleHTTPRequestHandler):
        """HTTP request handler to capture OAuth callback."""
        
        def do_GET(self):
            """Handle GET request from OAuth redirect."""
            # Parse the callback URL
            parsed_path = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed_path.query)
            
            # Extract authorization code or error
            if 'code' in query_params:
                code = query_params['code'][0]
                callback_data['code'] = code
                callback_data['received'] = True
                
                # Send success response
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write("""
                <html>
                <head><title>Authorization Successful</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1 style="color: #1DB954;">✓ Authorization Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                    <p style="color: #666; font-size: 14px;">The authorization code has been captured automatically.</p>
                </body>
                </html>
                """.encode())
            elif 'error' in query_params:
                error = query_params['error'][0]
                error_description = query_params.get('error_description', ['Unknown error'])[0]
                callback_data['error'] = error
                callback_data['error_description'] = error_description
                callback_data['received'] = True
                
                # Send error response
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(f"""
                <html>
                <head><title>Authorization Failed</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1 style="color: #d32f2f;">✗ Authorization Failed</h1>
                    <p><strong>Error:</strong> {error}</p>
                    <p>{error_description}</p>
                    <p>Please check the terminal for more information.</p>
                </body>
                </html>
                """.encode())
            else:
                # Unknown callback
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write("""
                <html>
                <head><title>Invalid Callback</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>Invalid Callback</h1>
                    <p>No authorization code or error found in callback URL.</p>
                </body>
                </html>
                """.encode())
        
        def log_message(self, format, *args):
            """Suppress default logging."""
            pass
    
    return CallbackHandler


def start_callback_server(port=8888, timeout=300):
    """
    Start a local HTTP server to capture OAuth callback.
    
    Args:
        port: Port to listen on (default: 8888)
        timeout: Maximum time to wait for callback in seconds (default: 300)
    
    Returns:
        tuple: (callback_data dict, server_thread)
    """
    callback_data = {'received': False, 'code': None, 'error': None, 'error_description': None}
    
    # Create handler class with callback_data closure
    handler_class = create_callback_handler(callback_data)
    
    server = socketserver.TCPServer(("127.0.0.1", port), handler_class)
    server.timeout = 1.0  # Check for shutdown every second
    
    def run_server():
        """Run the server until callback is received or timeout."""
        start_time = time.time()
        while not callback_data['received']:
            if time.time() - start_time > timeout:
                break
            server.handle_request()
        server.server_close()
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    return callback_data, server_thread


def main():
    """Main OAuth flow with automatic callback capture."""
    client_id, client_secret = get_credentials()
    
    print("\n" + "=" * 60)
    print("Starting OAuth flow with automatic callback capture...")
    print("=" * 60)
    print("\nA local server will start to automatically capture the authorization.")
    print("You will be redirected to Spotify to authorize the application.")
    print("After authorizing, you'll be redirected back and the script will continue automatically.\n")
    
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
    
    # Start callback server
    print("Starting local callback server on http://127.0.0.1:8888...")
    callback_data, server_thread = start_callback_server(port=8888, timeout=300)
    
    # Give server a moment to start
    time.sleep(0.5)
    
    # Open browser
    print("Opening browser for authorization...")
    print(f"\nIf the browser doesn't open automatically, visit this URL:\n{auth_url}\n")
    try:
        webbrowser.open(auth_url)
    except Exception as e:
        print(f"Warning: Could not open browser automatically: {e}")
        print(f"Please manually visit: {auth_url}")
    
    # Wait for callback
    print("Waiting for authorization callback...")
    print("(This may take up to 5 minutes. You can authorize in the browser now.)\n")
    
    # Wait for callback or timeout
    start_time = time.time()
    timeout = 300  # 5 minutes
    while not callback_data['received']:
        if time.time() - start_time > timeout:
            print("\n✗ Timeout waiting for authorization callback.")
            print("Please make sure you authorized the application in your browser.")
            return False
        time.sleep(0.5)
    
    # Check for errors
    if callback_data.get('error'):
        error = callback_data['error']
        error_desc = callback_data.get('error_description', 'Unknown error')
        print(f"\n✗ Authorization failed: {error}")
        print(f"Description: {error_desc}")
        return False
    
    # Extract authorization code
    code = callback_data.get('code')
    if not code:
        print("\n✗ Error: No authorization code received")
        return False
    
    print("✓ Authorization code received!")
    
    # Get access token and refresh token
    print("Exchanging authorization code for tokens...")
    try:
        token_info = sp_oauth.get_access_token(code)
    except Exception as e:
        print(f"✗ Error exchanging code for tokens: {e}")
        return False
    
    # get_access_token returns a dict with token info
    if isinstance(token_info, dict):
        if 'refresh_token' not in token_info:
            print("✗ Error: Failed to get refresh token")
            return False
        refresh_token = token_info['refresh_token']
    else:
        # If it returns just the token string, get cached token info
        cached_token = sp_oauth.get_cached_token()
        if not cached_token or 'refresh_token' not in cached_token:
            print("✗ Error: Failed to get refresh token")
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
        print("\n" + "=" * 60)
        print("✓ OAuth setup complete! You can now use the Spotify backend.")
        print("=" * 60)
        return True
    except Exception as e:
        print(f"✗ Error testing connection: {e}")
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

