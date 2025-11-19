#!/usr/bin/env python3
"""Simple GPIO button test script - tests button presses without affecting the main service."""
import sys
import time
import os
from gpiozero import Button
from signal import pause

# GPIO pins (matching the main player)
BUTTONS = {
    'play_pause': 17,
    'previous': 27,
    'next': 22,
    'cycle_source': 23
}

def test_button(name, pin):
    """Test a single button."""
    print(f"Testing {name} on GPIO {pin}...", end=' ', flush=True)
    try:
        # Try to close any existing GPIO resources first
        button = Button(pin, pull_up=True, bounce_time=0.1)
        
        def on_press():
            print(f"\n  ✓ {name} button PRESSED!", flush=True)
        
        button.when_pressed = on_press
        print("✓ OK")
        return button
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return None

def main():
    print("=" * 50)
    print("GPIO Button Test Script")
    print("=" * 50)
    print()
    print("This script will test all 4 buttons.")
    print("Press each button to verify it's working.")
    print("Press Ctrl+C to exit.")
    print()
    print("Button mapping:")
    for name, pin in BUTTONS.items():
        print(f"  {name:15} -> GPIO {pin}")
    print()
    
    # Check if service is running
    if os.system("systemctl is-active --quiet music-player.service") == 0:
        print("⚠ WARNING: music-player.service is still running!")
        print("   Stop it first with: sudo systemctl stop music-player.service")
        print()
    
    print("Waiting 2 seconds for GPIO to be ready...")
    time.sleep(2)
    print()
    print("Initializing buttons...")
    print("=" * 50)
    
    buttons = {}
    for name, pin in BUTTONS.items():
        btn = test_button(name, pin)
        if btn:
            buttons[name] = btn
        time.sleep(0.2)  # Small delay between button init
    
    if not buttons:
        print("ERROR: No buttons could be initialized!")
        print("Make sure:")
        print("  1. You have GPIO permissions (run with sudo or add user to gpio group)")
        print("  2. The GPIO pins are not already in use")
        print("  3. The wiring is correct")
        sys.exit(1)
    
    print(f"\n✓ {len(buttons)} button(s) ready for testing")
    print("\nPress the buttons now...\n")
    
    try:
        pause()
    except KeyboardInterrupt:
        print("\n\nTest interrupted. Exiting...")

if __name__ == '__main__':
    main()

