#!/usr/bin/env python3
"""Test script to verify ALSA volume changes with time-based limiting."""
import sys
import time
import subprocess
import re
from datetime import datetime, time as time_type
from unittest.mock import patch
from hardware.rotary_encoder import VolumeController

def get_alsa_volume():
    """Get current ALSA volume in dB."""
    try:
        result = subprocess.run(
            ['amixer', 'get', 'PCM', '0'],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        for line in result.stdout.split('\n'):
            if 'Playback' in line and 'dB' in line:
                db_match = re.search(r'\[(-?\d+\.?\d*)dB\]', line)
                if db_match:
                    return float(db_match.group(1))
        
        # Fallback: try percentage
        for line in result.stdout.split('\n'):
            if 'Playback' in line and '%' in line:
                percent_match = re.search(r'\[(\d+)%\]', line)
                if percent_match:
                    return int(percent_match.group(1))
        
        return None
    except Exception as e:
        print(f"Error getting ALSA volume: {e}")
        return None


def get_alsa_percentage():
    """Get current ALSA volume percentage."""
    try:
        result = subprocess.run(
            ['amixer', 'get', 'PCM', '0'],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        for line in result.stdout.split('\n'):
            if 'Playback' in line and '%' in line:
                percent_match = re.search(r'\[(\d+)%\]', line)
                if percent_match:
                    return int(percent_match.group(1))
        
        return None
    except Exception as e:
        print(f"Error getting ALSA percentage: {e}")
        return None


def main():
    """Test time-based volume limiting with ALSA."""
    print("=" * 70)
    print("ALSA Time-Based Volume Limiting Test")
    print("=" * 70)
    
    # Create volume controller
    vc = VolumeController()
    
    # Get current time info
    now = datetime.now()
    offset = vc._get_time_based_db_offset()
    
    print(f"\nCurrent Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Time-based dB offset: {offset}dB")
    print(f"Base max_db: {vc._base_max_db}dB")
    print(f"Effective max_db: {vc.max_db}dB")
    print(f"Expected max_db: {vc._base_max_db + offset}dB")
    
    # Get ALSA volume
    alsa_db = get_alsa_volume()
    alsa_percent = get_alsa_percentage()
    
    print(f"\nCurrent ALSA Volume:")
    if alsa_db is not None:
        print(f"  dB: {alsa_db}dB")
    if alsa_percent is not None:
        print(f"  Percentage: {alsa_percent}%")
    
    # Get volume controller's view
    vc_volume = vc.get_volume()
    print(f"\nVolumeController view:")
    print(f"  Volume: {vc_volume}%")
    
    # Check if volume exceeds limit
    if alsa_db is not None:
        if alsa_db > vc.max_db:
            print(f"\n⚠ WARNING: ALSA volume ({alsa_db}dB) exceeds max_db limit ({vc.max_db}dB)")
            print("  This should be automatically reduced by the time-based limiting thread.")
        else:
            print(f"\n✓ ALSA volume ({alsa_db}dB) is within max_db limit ({vc.max_db}dB)")
    
    # Test setting volume
    print("\n" + "=" * 70)
    print("Testing Volume Setting")
    print("=" * 70)
    
    print(f"\nCurrent volume: {vc_volume}%")
    print(f"Attempting to set volume to 100%...")
    
    old_volume = vc_volume
    result = vc.set_volume(100)
    new_volume = vc.get_volume()
    
    print(f"Result: {'Success' if result else 'Failed'}")
    print(f"New volume: {new_volume}%")
    
    # Check ALSA again
    new_alsa_db = get_alsa_volume()
    new_alsa_percent = get_alsa_percentage()
    
    if new_alsa_db is not None:
        print(f"\nNew ALSA Volume:")
        print(f"  dB: {new_alsa_db}dB")
        print(f"  Percentage: {new_alsa_percent}%")
        
        # Check if it was clamped
        if new_alsa_db <= vc.max_db:
            print(f"✓ Volume was properly limited to max_db ({vc.max_db}dB)")
        else:
            print(f"✗ Volume ({new_alsa_db}dB) exceeds max_db limit ({vc.max_db}dB)")
    
    # Show time schedule
    print("\n" + "=" * 70)
    print("Time-Based Volume Schedule")
    print("=" * 70)
    print("5pm-6pm:  0dB  (full volume)")
    print("6pm-7pm:  -7dB (reduced)")
    print("7pm-7am:  -14dB (night mode)")
    print("7am-8am:  -14dB (night mode)")
    print("8am-9am:  -7dB (reduced)")
    print("9am-5pm:  0dB  (full volume)")
    
    # Simulated time cycle
    print("\n" + "=" * 70)
    print("Simulating Time Changes (Press Ctrl+C to stop)")
    print("=" * 70)
    
    # Test times to cycle through (hour, minute, description)
    test_times = [
        (17, 0, "5:00 PM - Start of evening (0dB)"),
        (17, 30, "5:30 PM - Still full volume (0dB)"),
        (18, 0, "6:00 PM - First reduction (-7dB)"),
        (18, 30, "6:30 PM - Still reduced (-7dB)"),
        (19, 0, "7:00 PM - Night mode starts (-14dB)"),
        (20, 0, "8:00 PM - Night mode (-14dB)"),
        (23, 0, "11:00 PM - Night mode (-14dB)"),
        (2, 0, "2:00 AM - Night mode (-14dB)"),
        (6, 0, "6:00 AM - Still night mode (-14dB)"),
        (7, 0, "7:00 AM - Still night mode (-14dB)"),
        (7, 30, "7:30 AM - Still night mode (-14dB)"),
        (8, 0, "8:00 AM - Morning transition (-7dB)"),
        (8, 30, "8:30 AM - Still reduced (-7dB)"),
        (9, 0, "9:00 AM - Full volume restored (0dB)"),
        (12, 0, "12:00 PM - Full volume (0dB)"),
        (15, 0, "3:00 PM - Full volume (0dB)"),
    ]
    
    print(f"{'Simulated Time':<20} {'Offset':<10} {'Max dB':<10} {'Description':<35}")
    print("-" * 70)
    
    try:
        for hour, minute, description in test_times:
            # Create a mock datetime for this time
            test_datetime = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Patch datetime.now() to return our test time
            with patch('hardware.rotary_encoder.datetime') as mock_dt:
                # Set up the mock to return our test time for now()
                def mock_now():
                    return test_datetime
                mock_dt.now = mock_now
                # Keep the time class available
                mock_dt.time = time_type
                
                # Get the offset for this simulated time
                simulated_offset = vc._get_time_based_db_offset()
                simulated_max_db = vc._base_max_db + simulated_offset
                
                # Update the volume controller with this simulated time
                vc._update_time_based_limit()
                actual_max_db = vc.max_db
                
                # Get current ALSA values
                alsa_db = get_alsa_volume()
                alsa_percent = get_alsa_percentage()
                vc_vol = vc.get_volume()
                
                # Display the simulated time and values
                time_str = test_datetime.strftime('%H:%M')
                print(f"{time_str:<20} {simulated_offset:>6.1f}dB   {actual_max_db:>7.2f}dB   {description}")
                
                # Show ALSA values if available
                if alsa_db is not None:
                    status = "✓ OK" if alsa_db <= actual_max_db else "⚠ EXCEEDS"
                    print(f"  {'':20} {'ALSA:':<10} {alsa_db:>7.2f}dB ({alsa_percent}%) {status}")
                
                # Wait a bit to see the change
                time.sleep(2)
        
        print("\n" + "=" * 70)
        print("Time cycle complete. Looping...")
        print("=" * 70)
        print("(Press Ctrl+C to stop)")
        
        # Continuous loop
        iteration = 0
        while True:
            for hour, minute, description in test_times:
                test_datetime = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                with patch('hardware.rotary_encoder.datetime') as mock_dt:
                    def mock_now():
                        return test_datetime
                    mock_dt.now = mock_now
                    mock_dt.time = time_type
                    
                    simulated_offset = vc._get_time_based_db_offset()
                    vc._update_time_based_limit()
                    actual_max_db = vc.max_db
                    
                    alsa_db = get_alsa_volume()
                    alsa_percent = get_alsa_percentage()
                    vc_vol = vc.get_volume()
                    
                    time_str = test_datetime.strftime('%H:%M')
                    status = "✓" if alsa_db is not None and alsa_db <= actual_max_db else "⚠"
                    print(f"{time_str:<20} {simulated_offset:>6.1f}dB   {actual_max_db:>7.2f}dB   "
                          f"ALSA: {alsa_db:>7.2f}dB ({alsa_percent}%) {status}")
                    
                    time.sleep(2)
            
            iteration += 1
            print(f"\n--- Cycle {iteration} complete ---\n")
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n" + "=" * 70)
        print("Simulation stopped by user")
        print("=" * 70)
    
    # Cleanup
    vc.close()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

