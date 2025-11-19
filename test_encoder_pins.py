#!/usr/bin/env python3
"""Test script to monitor GPIO pins 5 and 6 for rotary encoder."""
import sys
import time
import os
from gpiozero import DigitalInputDevice

def main():
    print("=" * 60)
    print("Rotary Encoder GPIO Pin Test (KY-040)")
    print("=" * 60)
    print()
    print("Monitoring GPIO pins 5 (CLK) and 6 (DT)")
    print("Rotate the encoder to see state changes")
    print("Press Ctrl+C to exit")
    print()
    
    # Check if service is running
    if os.system("systemctl is-active --quiet music-player.service") == 0:
        print("⚠ WARNING: music-player.service is still running!")
        print("   Stop it first with: sudo systemctl stop music-player.service")
        print()
        response = input("Continue anyway? (y/N): ").strip().lower()
        if response != 'y':
            print("Exiting...")
            sys.exit(0)
        print()
    
    print("Initializing GPIO pins...")
    try:
        clk = DigitalInputDevice(5, pull_up=True)
        dt = DigitalInputDevice(6, pull_up=True)
        print("✓ GPIO pins initialized")
        print()
    except Exception as e:
        print(f"✗ Error initializing GPIO: {e}")
        sys.exit(1)
    
    print("Current pin states:")
    print(f"  GPIO 5 (CLK): {'HIGH' if clk.value else 'LOW'}")
    print(f"  GPIO 6 (DT):  {'HIGH' if dt.value else 'LOW'}")
    print()
    print("Monitoring for changes...")
    print("=" * 60)
    print()
    
    last_clk = clk.value
    last_dt = dt.value
    change_count = 0
    
    try:
        while True:
            current_clk = clk.value
            current_dt = dt.value
            
            # Detect changes
            if current_clk != last_clk or current_dt != last_dt:
                change_count += 1
                timestamp = time.strftime("%H:%M:%S")
                
                # Determine rotation direction
                direction = "?"
                if current_clk != last_clk:
                    if current_dt != current_clk:
                        direction = "CLOCKWISE (volume up)"
                    else:
                        direction = "COUNTER-CLOCKWISE (volume down)"
                
                print(f"[{timestamp}] Change #{change_count}: {direction}")
                print(f"  GPIO 5 (CLK): {'HIGH' if current_clk else 'LOW'} (was {'HIGH' if last_clk else 'LOW'})")
                print(f"  GPIO 6 (DT):  {'HIGH' if current_dt else 'LOW'} (was {'HIGH' if last_dt else 'LOW'})")
                print()
                
                last_clk = current_clk
                last_dt = current_dt
            
            time.sleep(0.01)  # Check every 10ms
            
    except KeyboardInterrupt:
        print("\n\nTest interrupted. Cleaning up...")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            clk.close()
            dt.close()
        except:
            pass
        print(f"Total changes detected: {change_count}")
        print("Done!")

if __name__ == '__main__':
    main()



