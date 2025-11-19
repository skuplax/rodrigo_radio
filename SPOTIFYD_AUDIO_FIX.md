# Spotifyd Audio Troubleshooting - Findings and Solutions

## Problem
Spotifyd connects and can be controlled from desktop app, but no audio output from 3.5mm jack on Raspberry Pi 4B.

## Root Causes Identified

### 1. Invalid Mixer Control (FIXED)
- **Issue**: Config had `onstart = "/usr/bin/amixer cset numid=3 1"` but `numid=3` doesn't exist
- **Fix**: Removed invalid commands, added `mixer = "PCM"` instead

### 2. Device Specification
- **Current**: `device = "hw:0,0"` 
- **Alternative**: `device = "default"` (uses ~/.asoundrc routing)
- **Test**: Try both to see which works better

### 3. ALSA Device Access
- ALSA device shows 8 subdevices available (should allow multiple processes)
- Device only opens when playback actually starts
- Need to verify spotifyd can successfully open device during playback

## Current Configuration

```ini
backend = "alsa"
device = "hw:0,0"
mixer = "PCM"
volume_controller = "alsa"
use_mpris = true
device_name = "Raspberry Pi"
bitrate = 96
cache_path = "/home/skayflakes/.cache/spotifyd/"
initial_volume = 75
```

## Diagnostic Steps

1. **Check if device opens during playback:**
   ```bash
   ./diagnose_spotifyd_audio.sh
   # Then try playing from Spotify and run again
   ```

2. **Monitor device status in real-time:**
   ```bash
   watch -n 0.5 'cat /proc/asound/card0/pcm0p/sub0/status 2>&1'
   ```

3. **Check for audio conflicts:**
   ```bash
   lsof /dev/snd/*
   ```

## Potential Solutions to Try

### Solution 1: Use "default" device (recommended first)
Change in `~/.config/spotifyd/spotifyd.conf`:
```ini
device = "default"
```
This uses your ~/.asoundrc routing which might work better.

### Solution 2: Use "plughw" for format conversion
```ini
device = "plughw:0,0"
```
This allows ALSA to automatically convert formats if needed.

### Solution 3: Check for exclusive access issues
If another process is using audio, spotifyd will fail silently. Check with:
```bash
lsof /dev/snd/*
```

### Solution 4: Verify format compatibility
Spotifyd uses S16_LE format at 44100 Hz. Hardware supports:
- Format: S16_LE ✓
- Rate: 8000-192000 Hz (44100 is supported) ✓
- Channels: 1-8 (2 channels for stereo) ✓

## Next Steps

1. Try playing music from Spotify desktop app
2. Run diagnostic script: `./diagnose_spotifyd_audio.sh`
3. Check if device opens: `cat /proc/asound/card0/pcm0p/sub0/status`
4. If still not working, try changing `device = "default"` or `device = "plughw:0,0"`



