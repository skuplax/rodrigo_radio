#!/bin/bash
# Diagnostic script for spotifyd audio issues

echo "=== Spotifyd Audio Diagnostic ==="
echo ""

echo "1. Checking spotifyd process..."
SPOTIFYD_PID=$(pgrep -f "spotifyd --no-daemon" | head -1)
if [ -z "$SPOTIFYD_PID" ]; then
    echo "   ERROR: spotifyd is not running"
    exit 1
else
    echo "   Found spotifyd PID: $SPOTIFYD_PID"
fi

echo ""
echo "2. Checking ALSA device status..."
if [ -f /proc/asound/card0/pcm0p/sub0/status ]; then
    STATUS=$(cat /proc/asound/card0/pcm0p/sub0/status 2>&1)
    echo "   Status: $STATUS"
    if [ -f /proc/asound/card0/pcm0p/sub0/hw_params ]; then
        echo "   Hardware params:"
        cat /proc/asound/card0/pcm0p/sub0/hw_params | sed 's/^/      /'
    fi
else
    echo "   Device not open (this is normal if not playing)"
fi

echo ""
echo "3. Checking open file descriptors..."
ls -la /proc/$SPOTIFYD_PID/fd/ 2>/dev/null | grep -E "snd|audio" || echo "   No ALSA file descriptors open"

echo ""
echo "4. Testing ALSA device access..."
timeout 2 aplay -D hw:0,0 /dev/zero -t raw -r 44100 -f S16_LE -c 2 2>&1 | head -3 || echo "   Test completed"

echo ""
echo "5. Current mixer settings..."
amixer -c 0 get PCM | grep -E "Playback|Mono" | head -2

echo ""
echo "6. Checking for audio conflicts..."
lsof /dev/snd/* 2>/dev/null | grep -v "spotifyd" | head -5 || echo "   No other processes using audio"

echo ""
echo "7. Recent spotifyd logs (last 20 lines)..."
journalctl --user -u spotifyd -n 20 --no-pager 2>&1 | tail -20 || systemctl --user status spotifyd --no-pager -l | tail -20

echo ""
echo "=== Diagnostic complete ==="
echo "Try playing music from Spotify now and run this script again to see if the device opens."



