#!/bin/bash
# Check Raspberry Pi audio configuration

echo "=== Raspberry Pi Audio Configuration Check ==="
echo ""

echo "1. Boot config audio settings:"
sudo grep -i "audio\|dtparam" /boot/firmware/config.txt 2>/dev/null | grep -v "^#" || echo "   No audio settings found"

echo ""
echo "2. Current audio output (raspi-config):"
if command -v raspi-config >/dev/null 2>&1; then
    AUDIO_OUT=$(sudo raspi-config nonint get_audio 2>&1)
    case $AUDIO_OUT in
        0) echo "   Auto (default)" ;;
        1) echo "   Force 3.5mm jack" ;;
        2) echo "   Force HDMI" ;;
        *) echo "   Unknown: $AUDIO_OUT" ;;
    esac
else
    echo "   raspi-config not available"
fi

echo ""
echo "3. ALSA cards:"
aplay -l 2>&1 | grep "^card"

echo ""
echo "4. Current default ALSA device:"
cat ~/.asoundrc 2>/dev/null || echo "   No ~/.asoundrc found"

echo ""
echo "5. Testing 3.5mm jack:"
echo "   Run: speaker-test -t sine -f 440 -l 1 -D hw:0,0"
echo "   (You should hear a tone if 3.5mm jack is working)"

echo ""
echo "=== Recommendation ==="
echo "If audio doesn't work, run: sudo raspi-config"
echo "Then: Advanced Options > Audio > Force 3.5mm ('headphone') jack"

