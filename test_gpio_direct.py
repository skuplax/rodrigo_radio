#!/usr/bin/env python3
"""Direct GPIO test to verify button state reading."""
import time
from gpiozero import Button

pins = [17, 27, 22, 23]
buttons = {}

print("Initializing buttons...")
for pin in pins:
    try:
        b = Button(pin, pull_up=True)
        buttons[pin] = b
        print(f"GPIO {pin}: OK")
    except Exception as e:
        print(f"GPIO {pin}: ERROR - {e}")

if not buttons:
    print("No buttons initialized!")
    exit(1)

print("\nReading button states every second...")
print("Press buttons to see state changes")
print("Press Ctrl+C to exit\n")

try:
    while True:
        for pin, btn in buttons.items():
            state = "PRESSED" if not btn.is_pressed else "RELEASED"
            print(f"GPIO {pin}: {state}", end="  ")
        print("\r", end="", flush=True)
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\n\nCleaning up...")
    for btn in buttons.values():
        btn.close()

