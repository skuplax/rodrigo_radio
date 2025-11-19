#!/usr/bin/env python3
"""Test script for rotary encoder volume control."""
import sys
import time
import os
from rotary_encoder import RotaryEncoder, VolumeController

def main():
    print("=" * 60)
    print("Rotary Encoder Volume Control Test")
    print("=" * 60)
    print()
    print("This script tests the rotary encoder for volume control.")
    print("Rotate the encoder to adjust volume, press switch to mute/unmute.")
    print("Press Ctrl+C to exit.")
    print()
    
    # Check if service is running
    if os.system("systemctl is-active --quiet music-player.service") == 0:
        print("⚠ WARNING: music-player.service is still running!")
        print("   Stop it first with: sudo systemctl stop music-player.service")
        print()
    
    # Get encoder pins from user
    print("Enter rotary encoder GPIO pins:")
    try:
        clk_pin = int(input("CLK pin (e.g., 5): ").strip())
        dt_pin = int(input("DT pin (e.g., 6): ").strip())
        sw_input = input("Switch pin (optional, press Enter to skip): ").strip()
        sw_pin = int(sw_input) if sw_input else None
        volume_step = int(input("Volume step (1-10, default 2): ").strip() or "2")
    except (ValueError, KeyboardInterrupt):
        print("\nInvalid input or cancelled. Exiting.")
        sys.exit(1)
    
    print()
    print("Initializing rotary encoder...")
    print(f"  CLK: GPIO{clk_pin}")
    print(f"  DT: GPIO{dt_pin}")
    if sw_pin:
        print(f"  Switch: GPIO{sw_pin}")
    print(f"  Volume step: {volume_step}%")
    print()
    
    try:
        # Test volume controller first
        print("Testing volume controller...")
        volume_ctrl = VolumeController()
        current_volume = volume_ctrl.get_volume()
        print(f"Current volume: {current_volume}%")
        print()
        
        # Initialize encoder
        encoder = RotaryEncoder(
            clk_pin=clk_pin,
            dt_pin=dt_pin,
            sw_pin=sw_pin,
            volume_step=volume_step
        )
        
        # Set up callbacks
        def on_volume_change(volume):
            print(f"Volume: {volume}%")
        
        def on_mute_toggle():
            print("Mute toggled!")
        
        encoder.on_volume_change = on_volume_change
        encoder.on_mute_toggle = on_mute_toggle
        
        print("✓ Rotary encoder initialized successfully!")
        print()
        print("Rotate the encoder to adjust volume...")
        if sw_pin:
            print("Press the encoder switch to mute/unmute...")
        print()
        print("Waiting for input (Ctrl+C to exit)...")
        print("=" * 60)
        print()
        
        # Wait for input
        from signal import pause
        pause()
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted. Cleaning up...")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        try:
            encoder.close()
        except:
            pass
        print("Done!")

if __name__ == '__main__':
    main()


