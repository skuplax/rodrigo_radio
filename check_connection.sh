#!/bin/bash
# Quick script to check if Spotify device is connected

echo "Checking Spotify device connection..."
echo ""

# Check if device is in API
python3 -c "
import sys
sys.path.insert(0, '/home/skayflakes/music-player')
from backends.spotify_backend import SpotifyBackend

try:
    backend = SpotifyBackend()
    device_id = backend._find_raspotify_device(retry=False)
    if device_id:
        print('✓ Device is connected!')
        sys.exit(0)
    else:
        print('✗ Device not found - connect from Spotify app first')
        sys.exit(1)
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
"


