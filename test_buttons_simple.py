#!/usr/bin/env python3
"""Simplified GPIO button test - tests one button at a time."""
import sys
import time
from gpiozero import Button
from signal import pause

BUTTONS = {
    'play_pause': 17,
    'previous': 27,
    'next': 22,
    'cycle_source': 23
}

def main():
    print("=" * 50)
    print("GPIO Button Test (Simple)")
    print("=" * 50)
    print()
    print("Initializing buttons one at a time...")
    print()
    
    buttons = {}
    failed = []
    
    for name, pin in BUTTONS.items():
        print(f"Setting up {name} (GPIO {pin})...", end=' ', flush=True)
        try:
            # Add small delay between each
            time.sleep(0.3)
            button = Button(pin, pull_up=True, bounce_time=0.1)
            
            def make_callback(btn_name):
                def callback():
                    print(f"\n>>> {btn_name.upper()} BUTTON PRESSED! <<<")
                return callback
            
            button.when_pressed = make_callback(name)
            buttons[name] = button
            print("✓")
        except Exception as e:
            print(f"✗ Error: {e}")
            failed.append((name, pin, str(e)))
    
    print()
    if failed:
        print(f"⚠ {len(failed)} button(s) failed to initialize:")
        for name, pin, error in failed:
            print(f"  {name} (GPIO {pin}): {error}")
        print()
    
    if not buttons:
        print("ERROR: No buttons could be initialized!")
        sys.exit(1)
    
    print(f"✓ {len(buttons)} button(s) ready for testing")
    print()
    print("Press the buttons now to test them...")
    print("Press Ctrl+C to exit")
    print("=" * 50)
    print()
    
    try:
        pause()
    except KeyboardInterrupt:
        print("\n\nCleaning up...")
        for button in buttons.values():
            try:
                button.close()
            except:
                pass
        print("Done!")

if __name__ == '__main__':
    main()

