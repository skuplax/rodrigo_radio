#!/bin/bash
# Safe button test script - stops service, tests buttons, restarts service

set -e

echo "Stopping music-player service..."
sudo systemctl stop music-player.service

echo "Waiting for GPIO to be released..."
sleep 2

echo ""
echo "Starting button test..."
echo "Press Ctrl+C when done testing"
echo ""

# Run the test script
python3 /home/skayflakes/music-player/test_buttons.py

echo ""
echo "Test complete. Restarting music-player service..."
sudo systemctl start music-player.service

sleep 1
if sudo systemctl is-active --quiet music-player.service; then
    echo "✓ Service restarted successfully"
else
    echo "✗ Service failed to restart. Check with: sudo systemctl status music-player.service"
fi

