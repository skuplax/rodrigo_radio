#!/usr/bin/env python3
"""CLI tool for monitoring player status and history."""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional
from core.sources import SourceManager, DEFAULT_STATE_FILE
from core.playback_history import PlaybackHistory

# Try to import player controller for live status
try:
    from core.player_controller import PlayerController
    CONTROLLER_AVAILABLE = True
except ImportError:
    CONTROLLER_AVAILABLE = False


def format_timestamp(iso_string: str) -> str:
    """Format ISO timestamp to human-readable format."""
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return iso_string


def show_status():
    """Show current player status."""
    print("=" * 60)
    print("MUSIC PLAYER STATUS")
    print("=" * 60)
    
    # Load state
    state_file = DEFAULT_STATE_FILE
    if not state_file.exists():
        print("\nNo state file found. Player may not be running.")
        return
    
    try:
        with open(state_file, 'r') as f:
            state = json.load(f)
        
        source_index = state.get('current_source_index', 0)
        last_updated = state.get('last_updated', 'Unknown')
        
        print(f"\nCurrent Source Index: {source_index}")
        print(f"Last Updated: {format_timestamp(last_updated)}")
        
    except Exception as e:
        print(f"\nError reading state: {e}")
    
    # Try to get live status from controller
    status_info = None
    if CONTROLLER_AVAILABLE:
        try:
            # Try to get status from running controller
            # Note: This requires the controller to be running
            # For now, we'll try to read from state files and show what we can
            pass
        except Exception:
            pass
    
    # Load sources to show current source name
    try:
        source_manager = SourceManager()
        current_source = source_manager.get_current_source()
        
        if current_source:
            print(f"\nCurrent Source: {current_source.get('label', 'Unknown')}")
            print(f"Source Type: {current_source.get('type', 'Unknown')}")
            print(f"Source ID: {current_source.get('id', 'Unknown')}")
        else:
            print("\nNo current source configured")
        
        # Try to get playback info from backends directly
        playback_status = "Unknown"
        current_item = None
        playback_info = None
        
        try:
            # Try to initialize backend to get current status
            source_type = current_source.get('type') if current_source else None
            
            if source_type == 'spotify_playlist':
                from backends.spotify_backend import SpotifyBackend
                try:
                    backend = SpotifyBackend()
                    # Get playback info first (it updates current item and gets fresh data)
                    playback_info = backend.get_playback_info()
                    # Get current item (updated by get_playback_info)
                    current_item = backend.get_current_item()
                    # Check playing status
                    is_playing = backend.is_playing()
                    playback_status = "Playing" if is_playing else "Paused/Stopped"
                except Exception as e:
                    import traceback
                    playback_status = f"Error accessing Spotify: {str(e)[:50]}"
                    # Debug: uncomment to see full error
                    # traceback.print_exc()
            elif source_type in ('youtube_channel', 'youtube_playlist'):
                from backends.youtube_backend import YouTubeBackend
                try:
                    backend = YouTubeBackend()
                    is_playing = backend.is_playing()
                    playback_status = "Playing" if is_playing else "Paused/Stopped"
                    # Get playback info first (it also updates current item if available)
                    playback_info = backend.get_playback_info()
                    current_item = backend.get_current_item()
                except Exception as e:
                    playback_status = f"Error accessing YouTube: {str(e)[:50]}"
            else:
                playback_status = "Not available for this source type"
        except Exception as e:
            # Backend initialization failed, that's okay
            playback_status = "Unable to determine (backend not accessible)"
        
        print(f"\nPlayback Status: {playback_status}")
        
        # Show current item if available (even if paused)
        if current_item:
            print(f"Now Playing: {current_item}")
        elif playback_info is not None:
            # playback_info exists but no current_item means we got API response but no track
            if source_type == 'spotify_playlist':
                print("Now Playing: (No track loaded)")
        elif playback_status in ("Playing", "Paused/Stopped") and source_type == 'spotify_playlist':
            # Spotify backend was accessible but returned no info
            print("Now Playing: (No track information available)")
        elif playback_status in ("Playing", "Paused/Stopped") and source_type in ('youtube_channel', 'youtube_playlist'):
            print("Now Playing: (YouTube playback info not available)")
        
        # Show playback position/duration if available
        if playback_info:
            position = playback_info.get('position')
            duration = playback_info.get('duration')
            position_ms = playback_info.get('position_ms')
            duration_ms = playback_info.get('duration_ms')
            progress = playback_info.get('progress')
            
            # Only show if we have valid data
            if position_ms is not None and duration_ms is not None:
                # Validate data
                if position_ms <= duration_ms and position and duration:
                    print(f"Position: {position} / {duration}")
                    if progress is not None and 0 <= progress <= 100:
                        # Create a simple progress bar
                        bar_length = 30
                        filled = int(bar_length * progress / 100)
                        bar = '█' * filled + '░' * (bar_length - filled)
                        print(f"Progress: [{bar}] {progress:.1f}%")
                elif position and duration:
                    # Data validation failed but we have formatted strings, show with warning
                    print(f"Position: {position} / {duration} (data validation failed)")
            elif position and duration:
                # We have formatted strings but not raw ms values
                print(f"Position: {position} / {duration}")
                if progress is not None and 0 <= progress <= 100:
                    # Create a simple progress bar
                    bar_length = 30
                    filled = int(bar_length * progress / 100)
                    bar = '█' * filled + '░' * (bar_length - filled)
                    print(f"Progress: [{bar}] {progress:.1f}%")
            elif position:
                print(f"Position: {position}")
            elif duration:
                print(f"Duration: {duration}")
        
        sources = source_manager.get_sources()
        print(f"\nTotal Sources: {len(sources)}")
        
        if sources:
            print("\nAll Sources:")
            for i, source in enumerate(sources):
                marker = " <-- CURRENT" if i == source_index else ""
                print(f"  {i}. {source.get('label', 'Unknown')} ({source.get('type', 'Unknown')}){marker}")
    
    except Exception as e:
        print(f"\nError loading sources: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)


def show_dashboard():
    """Show interactive dashboard (refreshes every 2 seconds)."""
    import time
    
    try:
        while True:
            # Clear screen (ANSI escape code)
            print("\033[2J\033[H", end='')
            
            show_status()
            
            # Show recent history
            print("\nRECENT PLAYBACK HISTORY")
            print("=" * 60)
            
            try:
                history = PlaybackHistory()
                recent = history.get_recent(limit=10)
                
                if recent:
                    for entry in recent:
                        timestamp = format_timestamp(entry.get('timestamp', ''))
                        action = entry.get('action', 'unknown')
                        event_type = entry.get('event_type', '')
                        source_label = entry.get('source_label') or 'Unknown'
                        item_name = entry.get('item_name') or ''
                        
                        if action == 'playback_start':
                            item_str = f" - {item_name}" if item_name else ""
                            print(f"{timestamp} | PLAY | {source_label}{item_str}")
                        elif action == 'source_change':
                            print(f"{timestamp} | SOURCE CHANGE | {source_label}")
                        elif event_type == 'user_input':
                            action_display = action.replace('_', ' ').upper()
                            if source_label and source_label != 'Unknown':
                                print(f"{timestamp} | {action_display} | {source_label}")
                            else:
                                print(f"{timestamp} | {action_display}")
                        elif action in ('pause', 'resume', 'next', 'previous'):
                            print(f"{timestamp} | {action.upper()} | {source_label}")
                        else:
                            event_prefix = f"[{event_type.upper()}] " if event_type else ""
                            print(f"{timestamp} | {event_prefix}{action.replace('_', ' ').upper()}")
                else:
                    print("No history available")
            
            except Exception as e:
                print(f"Error loading history: {e}")
            
            print("\n" + "=" * 60)
            print("Press Ctrl+C to exit")
            print("Refreshing in 2 seconds...")
            
            time.sleep(2)
    
    except KeyboardInterrupt:
        print("\n\nDashboard closed.")


def show_history(limit: int = 50):
    """Show playback history."""
    print("=" * 60)
    print(f"PLAYBACK HISTORY (Last {limit} entries)")
    print("=" * 60)
    
    try:
        history = PlaybackHistory()
        entries = history.get_recent(limit=limit)
        
        if not entries:
            print("\nNo history available.")
            return
        
        print()
        for entry in entries:
            timestamp = format_timestamp(entry.get('timestamp', ''))
            action = entry.get('action', 'unknown')
            event_type = entry.get('event_type', '')
            source_label = entry.get('source_label') or 'Unknown'
            item_name = entry.get('item_name') or ''
            value = entry.get('value')
            duration_ms = entry.get('duration_ms')
            
            # Format based on event type and action
            if action == 'playback_start':
                item_str = f" - {item_name}" if item_name else ""
                print(f"{timestamp} | PLAY | {source_label}{item_str}")
            elif action == 'source_change':
                print(f"{timestamp} | SOURCE CHANGE | {source_label}")
            elif event_type == 'user_input':
                # User input events
                action_display = action.replace('_', ' ').upper()
                if source_label and source_label != 'Unknown':
                    print(f"{timestamp} | {action_display} | {source_label}")
                else:
                    print(f"{timestamp} | {action_display}")
            elif event_type == 'audio':
                # Audio events
                if value is not None:
                    if action in ('volume_set', 'volume_adjust'):
                        print(f"{timestamp} | {action.replace('_', ' ').upper()} | {value:.0f}%")
                    else:
                        print(f"{timestamp} | {action.replace('_', ' ').upper()}")
                else:
                    print(f"{timestamp} | {action.replace('_', ' ').upper()}")
            elif event_type == 'performance' and duration_ms:
                print(f"{timestamp} | {action.replace('_', ' ').upper()} | {duration_ms:.2f}ms")
            elif event_type == 'network':
                status = entry.get('status', '')
                print(f"{timestamp} | {action.replace('_', ' ').upper()} | {status}")
            elif action in ('pause', 'resume', 'next', 'previous'):
                print(f"{timestamp} | {action.upper()} | {source_label}")
            else:
                # Generic display
                event_prefix = f"[{event_type.upper()}] " if event_type else ""
                print(f"{timestamp} | {event_prefix}{action.replace('_', ' ').upper()}")
        
        print("\n" + "=" * 60)
    
    except Exception as e:
        print(f"Error loading history: {e}")


def cache_sources(force: bool = False):
    """Manually trigger Piper TTS cache generation for all sources."""
    from utils.announcements import generate_cached_audio, ensure_cache_directory, get_cache_path
    
    print("=" * 60)
    print("GENERATING PIPER TTS CACHE FOR SOURCES")
    print("=" * 60)
    
    try:
        source_manager = SourceManager()
        sources = source_manager.get_sources()
        
        if not sources:
            print("\nNo sources configured.")
            return
        
        print(f"\nFound {len(sources)} sources")
        print("Generating cache files...\n")
        
        ensure_cache_directory()
        missing_count = 0
        cached_count = 0
        failed_count = 0
        
        for i, source in enumerate(sources, 1):
            source_label = source.get('label', source.get('id', 'Unknown source'))
            cache_path = get_cache_path(source_label)
            
            # Check if already cached
            if not force and cache_path.exists() and cache_path.stat().st_size > 0:
                print(f"[{i}/{len(sources)}] ✓ Already cached: {source_label}")
                cached_count += 1
            else:
                # If forcing, delete existing cache file to force regeneration
                if force and cache_path.exists():
                    try:
                        cache_path.unlink()
                        print(f"[{i}/{len(sources)}] Regenerating: {source_label}...", end=' ', flush=True)
                    except Exception as e:
                        print(f"[{i}/{len(sources)}] Warning: Could not delete existing cache for {source_label}: {e}")
                        print(f"[{i}/{len(sources)}] Generating: {source_label}...", end=' ', flush=True)
                else:
                    print(f"[{i}/{len(sources)}] Generating: {source_label}...", end=' ', flush=True)
                
                if generate_cached_audio(source_label):
                    print("✓")
                    cached_count += 1
                else:
                    print("✗ Failed")
                    failed_count += 1
                    missing_count += 1
        
        print("\n" + "=" * 60)
        print(f"Cache generation complete:")
        print(f"  ✓ Cached: {cached_count}")
        if missing_count > 0:
            print(f"  ✗ Failed: {failed_count}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError generating cache: {e}")
        import traceback
        traceback.print_exc()


def change_source(source_identifier):
    """Change the current source/channel."""
    print("=" * 60)
    print("CHANGE SOURCE/CHANNEL")
    print("=" * 60)
    
    try:
        source_manager = SourceManager()
        sources = source_manager.get_sources()
        
        if not sources:
            print("\n✗ No sources configured.")
            print(f"   Create a sources.json file at: {source_manager.sources_file}")
            return
        
        # Show current source
        current_source = source_manager.get_current_source()
        if current_source:
            current_index = source_manager._current_index
            print(f"\nCurrent Source: [{current_index}] {current_source.get('label', 'Unknown')}")
        else:
            print("\nCurrent Source: None")
        
        # Show all sources
        print(f"\nAvailable Sources ({len(sources)}):")
        for i, source in enumerate(sources):
            marker = " <-- CURRENT" if i == source_manager._current_index else ""
            source_type = source.get('type', 'unknown')
            source_label = source.get('label', source.get('id', 'Unknown'))
            print(f"  [{i}] {source_label} ({source_type}){marker}")
        
        # Try to set the source
        print(f"\nSetting source to: {source_identifier}")
        result = source_manager.set_source(source_identifier)
        
        if result:
            print(f"\n✓ Successfully changed to: {result.get('label', result.get('id', 'Unknown'))}")
            print(f"  Type: {result.get('type', 'Unknown')}")
            print(f"  Index: {source_manager._current_index}")
            print("\n" + "=" * 60)
            print("Note: The player will pick up this change on the next source cycle")
            print("      or when it checks for state changes.")
            print("=" * 60)
        else:
            print(f"\n✗ Failed to change source")
            print("\nUsage:")
            print("  python3 cli.py change-source <index>")
            print("  python3 cli.py change-source <source_id>")
            print("  python3 cli.py change-source <source_label>")
            print("\nExamples:")
            print("  python3 cli.py change-source 0")
            print("  python3 cli.py change-source gospel_spotify")
            print("  python3 cli.py change-source \"Spotify – Gospel\"")
            print("=" * 60)
    
    except Exception as e:
        print(f"\n✗ Error changing source: {e}")
        import traceback
        traceback.print_exc()


def test_spotify():
    """Test Spotify connection and configuration."""
    print("=" * 60)
    print("SPOTIFY CONNECTION TEST")
    print("=" * 60)
    
    import subprocess
    import json
    import time
    from pathlib import Path
    
    # Try to import spotipy
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        SPOTIPY_AVAILABLE = True
    except ImportError:
        print("\n✗ spotipy is not installed")
        print("  Install with: pip3 install --user --break-system-packages spotipy")
        return
    
    # Check config file
    _PROJECT_DIR = Path(__file__).parent.absolute()
    CONFIG_FILE = _PROJECT_DIR / "config" / "spotify_api_config.json"
    
    print("\n1. Checking configuration file...")
    if not CONFIG_FILE.exists():
        print(f"   ✗ Config file not found: {CONFIG_FILE}")
        print("   Run: python3 scripts/spotify_oauth_setup.py")
        return
    else:
        print(f"   ✓ Config file found: {CONFIG_FILE}")
    
    # Load config
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        
        required_keys = ['client_id', 'client_secret', 'refresh_token']
        missing = [key for key in required_keys if key not in config]
        if missing:
            print(f"   ✗ Missing required keys: {missing}")
            return
        
        print("   ✓ All required configuration keys present")
        print(f"   Client ID: {config['client_id'][:8]}...")
        
    except Exception as e:
        print(f"   ✗ Error loading config: {e}")
        return
    
    # Test API authentication
    print("\n2. Testing Spotify Web API authentication...")
    try:
        cache_path = _PROJECT_DIR / ".spotify_cache"
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
        
        spotify = spotipy.Spotify(auth_manager=auth_manager)
        user = spotify.current_user()
        print(f"   ✓ Authentication successful")
        print(f"   User: {user.get('display_name', 'Unknown')} ({user.get('id', 'Unknown')})")
        print(f"   Email: {user.get('email', 'N/A')}")
        print(f"   Product: {user.get('product', 'N/A')}")
        
    except Exception as e:
        error_str = str(e).lower()
        if 'invalid_grant' in error_str or ('refresh_token' in error_str and ('expired' in error_str or 'invalid' in error_str)):
            print("   ✗ Refresh token has expired")
            print("   Run: python3 scripts/spotify_oauth_setup.py")
        else:
            print(f"   ✗ Authentication failed: {e}")
        return
    
    # Check raspotify service
    print("\n3. Checking raspotify service...")
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', '--quiet', 'raspotify'],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print("   ✓ raspotify service is running")
        else:
            print("   ✗ raspotify service is not running")
            print("   Start with: sudo systemctl start raspotify")
    except FileNotFoundError:
        # Try alternative method
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'librespot'],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print("   ✓ raspotify process is running (checked via pgrep)")
            else:
                print("   ✗ raspotify process not found")
        except Exception:
            print("   ? Could not check raspotify status (systemctl/pgrep not available)")
    except Exception as e:
        print(f"   ? Could not check raspotify status: {e}")
    
    # Try to find device
    print("\n4. Finding raspotify device in Spotify API...")
    try:
        devices = spotify.devices()
        available_devices = devices.get('devices', [])
        
        if not available_devices:
            print("   ⚠ No devices found in Spotify API")
            print("   Make sure raspotify is running and visible in Spotify app")
        else:
            print(f"   Found {len(available_devices)} device(s):")
            found_raspotify = False
            for device in available_devices:
                device_name = device.get('name', 'Unknown')
                device_id = device.get('id', 'Unknown')
                device_type = device.get('type', 'Unknown')
                is_active = device.get('is_active', False)
                is_restricted = device.get('is_restricted', False)
                
                # Check if this looks like raspotify
                keywords = ['raspotify', 'raspberry', 'librespot', 'pi', "rodrigo's radio", 'rodrigo radio']
                is_raspotify = any(keyword.lower() in device_name.lower() for keyword in keywords)
                
                status = "ACTIVE" if is_active else "inactive"
                marker = " <-- RASPOTIFY" if is_raspotify else ""
                
                print(f"     - {device_name} ({device_type}) [{status}]{marker}")
                
                if is_raspotify:
                    found_raspotify = True
                    if is_active:
                        print(f"       Device ID: {device_id}")
            
            if not found_raspotify:
                print("   ⚠ Raspotify device not found in available devices")
                print("   It may need to be activated in the Spotify app")
            else:
                print("   ✓ Raspotify device found")
    
    except Exception as e:
        print(f"   ✗ Error finding device: {e}")
    
    # Test API permissions
    print("\n5. Testing API permissions...")
    try:
        # Test playback state
        playback = spotify.current_playback()
        if playback:
            print("   ✓ Can read current playback state")
            if playback.get('device'):
                print(f"     Currently playing on: {playback['device'].get('name', 'Unknown')}")
        else:
            print("   ✓ Can read playback state (no active playback)")
        
        # Test user profile
        user_profile = spotify.current_user()
        print("   ✓ Can read user profile")
        
    except Exception as e:
        print(f"   ✗ Error testing API permissions: {e}")
    
    # Test actual playback (if device found and not currently playing)
    print("\n6. Testing playback functionality...")
    try:
        # Get current playback state
        playback = spotify.current_playback()
        is_currently_playing = playback and playback.get('is_playing', False)
        
        if is_currently_playing:
            print("   ⚠ Spotify is currently playing - skipping playback test")
            print(f"     Currently playing: {playback.get('item', {}).get('name', 'Unknown')}")
        else:
            # Find raspotify device
            devices = spotify.devices()
            available_devices = devices.get('devices', [])
            
            raspotify_device = None
            for device in available_devices:
                device_name = device.get('name', 'Unknown')
                keywords = ['raspotify', 'raspberry', 'librespot', 'pi', "rodrigo's radio", 'rodrigo radio']
                if any(keyword.lower() in device_name.lower() for keyword in keywords):
                    raspotify_device = device
                    break
            
            if not raspotify_device:
                print("   ⚠ Raspotify device not found - cannot test playback")
                print("   Device needs to be activated from Spotify app first")
            else:
                device_id = raspotify_device.get('id')
                device_name = raspotify_device.get('name')
                is_active = raspotify_device.get('is_active', False)
                
                print(f"   Found device: {device_name} ({'active' if is_active else 'inactive'})")
                
                if not is_active:
                    print("   Attempting to activate device...")
                    try:
                        spotify.transfer_playback(device_id=device_id, force_play=False)
                        time.sleep(1)  # Wait for transfer
                        print("   ✓ Device activated")
                    except Exception as e:
                        print(f"   ⚠ Could not activate device: {e}")
                        print("   Device may need manual activation from Spotify app")
                
                # Try to play a test track
                # Use a known short track URI for testing
                # Using "Never Gonna Give You Up" by Rick Astley (short, well-known track)
                test_track_uri = "spotify:track:4cOdK2wGLETKBW3PvgPWqT"
                print("   Starting playback test (will play for 5 seconds)...")
                
                try:
                    # Try to play the test track
                    spotify.start_playback(device_id=device_id, uris=[test_track_uri])
                    track_name = "Never Gonna Give You Up"
                except Exception as play_error:
                    # If playing specific track fails, try to just start/resume playback
                    try:
                        spotify.start_playback(device_id=device_id)
                        track_name = "Current playback"
                    except Exception:
                        print(f"   ✗ Could not start playback: {play_error}")
                        raise
                
                # Wait 5 seconds and check if playback is actually happening
                print("   Waiting 5 seconds to verify playback...")
                time.sleep(5)
                
                # Check playback state
                playback_check = spotify.current_playback()
                if playback_check and playback_check.get('is_playing', False):
                    current_device = playback_check.get('device', {})
                    if current_device.get('id') == device_id:
                        print("   ✓ Playback test successful!")
                        if playback_check.get('item'):
                            item = playback_check['item']
                            print(f"     Playing: {item.get('name', 'Unknown')} by {', '.join([a['name'] for a in item.get('artists', [])])}")
                        else:
                            print(f"     Playing on: {current_device.get('name', 'Unknown')}")
                        
                        # Stop playback
                        print("   Stopping test playback...")
                        try:
                            spotify.pause_playback(device_id=device_id)
                            time.sleep(0.5)
                            print("   ✓ Playback stopped")
                        except Exception as stop_error:
                            print(f"   ⚠ Could not stop playback: {stop_error}")
                    else:
                        print("   ⚠ Playback started but on different device")
                        print(f"     Expected: {device_name}, Got: {current_device.get('name', 'Unknown')}")
                else:
                    print("   ✗ Playback test failed - playback did not start")
                    print("   Device may not be properly activated")
                    
    except Exception as e:
        print(f"   ✗ Playback test error: {e}")
        import traceback
        traceback.print_exc()
    
    except Exception as e:
        print(f"   ✗ Playback test error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("✓ Spotify connection test completed")
    print("=" * 60)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Music Player CLI Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status          Show current status
  %(prog)s dashboard       Show live dashboard (refreshes every 2s)
  %(prog)s history         Show last 50 history entries
  %(prog)s history -n 100  Show last 100 history entries
  %(prog)s cache           Generate Piper TTS cache for all sources
  %(prog)s cache -f        Force regenerate all cache files
  %(prog)s test-spotify    Test Spotify connection and configuration
  %(prog)s change-source 0 Change to source at index 0
  %(prog)s change-source "Spotify – Gospel"  Change to source by label
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Status command
    subparsers.add_parser('status', help='Show current player status')
    
    # Dashboard command
    subparsers.add_parser('dashboard', help='Show live dashboard (Ctrl+C to exit)')
    
    # History command
    history_parser = subparsers.add_parser('history', help='Show playback history')
    history_parser.add_argument(
        '-n', '--limit',
        type=int,
        default=50,
        help='Number of entries to show (default: 50)'
    )
    
    # Cache command
    cache_parser = subparsers.add_parser('cache', help='Generate Piper TTS cache for all sources')
    cache_parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='Force regeneration of existing cache files'
    )
    
    # Test Spotify command
    subparsers.add_parser('test-spotify', help='Test Spotify connection and configuration')
    
    # Change source command
    change_source_parser = subparsers.add_parser('change-source', help='Change the current source/channel')
    change_source_parser.add_argument(
        'source',
        help='Source identifier: index (0-based), source ID, or source label (partial match supported)'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'status':
        show_status()
    elif args.command == 'dashboard':
        show_dashboard()
    elif args.command == 'history':
        show_history(args.limit)
    elif args.command == 'cache':
        cache_sources(force=args.force)
    elif args.command == 'test-spotify':
        test_spotify()
    elif args.command == 'change-source':
        # Try to parse as integer first, otherwise use as string
        try:
            source_id = int(args.source)
        except ValueError:
            source_id = args.source
        change_source(source_id)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()

