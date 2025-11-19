#!/usr/bin/env python3
"""Test script to debug GMA News YouTube channel playback."""
import sys
sys.path.insert(0, '/home/skayflakes/music-player')

from backends.youtube_backend import YouTubeBackend
import time

print("Testing GMA News channel: UCqYw-CTd1dU2yGI71sEyqNw")
print("=" * 60)

backend = YouTubeBackend()

# Test the play method
print("\n1. Testing play() method...")
success = backend.play(
    'UCqYw-CTd1dU2yGI71sEyqNw',
    source_type='youtube_channel',
    channel_id='UCqYw-CTd1dU2yGI71sEyqNw'
)

if success:
    print("✓ Playback started successfully!")
    print(f"  Current item: {backend.get_current_item()}")
    print(f"  Is playing: {backend.is_playing()}")
    
    print("\n2. Waiting 5 seconds to verify playback...")
    time.sleep(5)
    
    print(f"  Still playing: {backend.is_playing()}")
    
    print("\n3. Testing pause...")
    if backend.pause():
        print("✓ Paused successfully")
        time.sleep(2)
        
        print("\n4. Testing resume...")
        if backend.resume():
            print("✓ Resumed successfully")
            time.sleep(2)
    
    print("\n5. Stopping playback...")
    backend.stop()
    print("✓ Stopped")
else:
    print("✗ Failed to start playback")
    sys.exit(1)

print("\n" + "=" * 60)
print("Test completed successfully!")

