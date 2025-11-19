#!/usr/bin/env python3
"""Test script to check Spotify device connection and automatic activation."""
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from backends.spotify_backend import SpotifyBackend
from backends.base import BackendError

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """Test Spotify connection."""
    print("=" * 60)
    print("Testing Spotify Device Connection")
    print("=" * 60)
    print()
    
    try:
        print("1. Initializing Spotify backend...")
        backend = SpotifyBackend()
        print("   ✓ Backend initialized")
        print()
        
        print("2. Checking if raspotify service is running...")
        if backend._check_raspotify_running():
            print("   ✓ Raspotify service is running")
        else:
            print("   ✗ Raspotify service is NOT running")
            print("   → Start it with: sudo systemctl start raspotify")
            return 1
        print()
        
        print("3. Attempting to find raspotify device in Spotify API...")
        print("   (This will retry automatically with exponential backoff)")
        print()
        
        device_id = backend._find_raspotify_device(retry=True)
        
        if device_id:
            print(f"   ✓ Device found! ID: {device_id}")
            print()
            print("4. Testing device connection...")
            try:
                backend._ensure_device(retry=False)
                print("   ✓ Device connection verified")
                print()
                print("=" * 60)
                print("SUCCESS: Spotify device is connected and ready!")
                print("=" * 60)
                return 0
            except BackendError as e:
                print(f"   ✗ Device connection failed: {e}")
                return 1
        else:
            print("   ✗ Device not found in Spotify API")
            print()
            print("4. Checking for MPRIS fallback...")
            if backend._mpris_player:
                print("   ✓ MPRIS interface available (fallback control enabled)")
                print()
                print("=" * 60)
                print("PARTIAL: Device not in API, but MPRIS fallback available")
                print("Basic controls will work, but starting playlists may fail.")
                print("=" * 60)
                print()
                print("To fully activate:")
                print("1. Open Spotify app (mobile or desktop)")
                print("2. Look for 'Raspberry Pi' device in device list")
                print("3. Connect to it (play something)")
                print("4. After first connection, it should work automatically")
                return 0
            else:
                print("   ✗ MPRIS interface not available")
                print()
                print("=" * 60)
                print("ACTION REQUIRED: Device needs manual activation")
                print("=" * 60)
                print()
                print("Steps to activate:")
                print("1. Open Spotify app (mobile or desktop)")
                print("2. Look for 'Raspberry Pi' device in device list")
                print("3. Connect to it (play something on it)")
                print("4. Once connected, run this test again")
                print()
                print("After first activation, the device should work")
                print("automatically on subsequent boots.")
                return 1
                
    except BackendError as e:
        print(f"✗ Error: {e}")
        return 1
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())


