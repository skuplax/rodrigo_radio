# Raspberry Pi Music Player

A headless music and news player for Raspberry Pi controlled by physical buttons.

## Features

- **4-button control**: Play/Pause, Previous, Next, Cycle Source
- **Multiple sources**: Spotify playlists, YouTube channels, YouTube playlists
- **Auto-resume**: Automatically starts playing the last selected source on boot
- **Live stream detection**: Automatically plays live YouTube streams when available
- **Error handling**: Automatic retry with fallback to next source
- **CLI dashboard**: Monitor status and playback history

## Hardware Requirements

- Raspberry Pi 4B (or compatible)
- 4x 12mm momentary buttons
- 3.5mm audio jack (or HDMI audio)
- Wiring for buttons to GPIO pins (default: 17, 27, 22, 23)

## Software Dependencies

### System Packages

```bash
sudo apt update
sudo apt install -y \
    yt-dlp \
    mpv \
    python3-gpiozero \
    python3-dbus \
    python3-pip
```

**Note:** `spotifyd` is optional and may not be available in default repositories. It's only needed if you want to use Spotify sources. The installation script will attempt to install it, but will continue if it's not available. You can install it manually later if needed (see Troubleshooting section).

### Python Packages

```bash
pip3 install --user gpiozero
# dbus-python is usually available via apt, but if needed:
# pip3 install --user dbus-python
```

## Installation

### Automated Installation (Recommended)

1. **Navigate to the project directory**:
   ```bash
   cd /home/pi/music-player
   ```

2. **Install system packages** (run as root or with sudo):
   ```bash
   sudo ./install.sh
   ```
   This will install all required system packages.

3. **Complete user setup** (run as pi user, still in the project directory):
   ```bash
   ./install.sh
   ```
   This will:
   - Install Python packages
   - Set up configuration files
   - Install and optionally enable the systemd service
   - Configure spotifyd (if desired)

3. **Configure your sources**:
   ```bash
   nano /home/pi/music-player/sources.json
   ```
   Edit the file with your Spotify playlist IDs and YouTube channel/playlist IDs.

4. **Configure Spotify** (if using Spotify):
   ```bash
   nano ~/.config/spotifyd/spotifyd.conf
   ```
   Add your Spotify username and password.

### Manual Installation

If you prefer to install manually:

1. **Install system packages**:
   ```bash
   sudo apt update
   sudo apt install -y spotifyd yt-dlp mpv python3-gpiozero python3-dbus python3-pip
   ```

2. **Install Python packages**:
   ```bash
   pip3 install --user gpiozero
   ```

3. **Clone or copy this directory to `/home/pi/music-player`**

4. **Make scripts executable**:
   ```bash
   chmod +x /home/pi/music-player/player.py
   chmod +x /home/pi/music-player/cli.py
   ```

5. **Configure sources**:
   ```bash
   cp /home/pi/music-player/sources.json.example /home/pi/music-player/sources.json
   nano /home/pi/music-player/sources.json
   ```

6. **Configure spotifyd**:
   ```bash
   mkdir -p ~/.config/spotifyd
   cp /home/pi/music-player/spotifyd.conf.example ~/.config/spotifyd/spotifyd.conf
   nano ~/.config/spotifyd/spotifyd.conf
   ```

7. **Start spotifyd** (user service):
   ```bash
   systemctl --user enable spotifyd
   systemctl --user start spotifyd
   ```

8. **Install systemd service**:
   ```bash
   sudo cp /home/pi/music-player/music-player.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable music-player.service
   sudo systemctl start music-player.service
   ```

## Configuration

### Button GPIO Pins

Default pins (can be changed in `buttons.py` or `player_controller.py`):
- Button 1 (Play/Pause): GPIO 17
- Button 2 (Previous): GPIO 27
- Button 3 (Next): GPIO 22
- Button 4 (Cycle Source): GPIO 23

### Sources Configuration

Edit `/home/pi/music-player/sources.json`:

- **Spotify Playlist**: Requires `playlist_id` (full URI or just ID)
- **YouTube Channel**: Requires `channel_id` (starts with `UC`)
- **YouTube Playlist**: Requires `playlist_id` (starts with `PL`)

### Audio Output

Ensure audio is configured to use the 3.5mm jack:
```bash
sudo raspi-config
# Navigate to: Advanced Options > Audio > Force 3.5mm jack
```

Or manually in `/boot/config.txt`:
```
dtparam=audio=on
```

## Usage

### CLI Tool

The CLI tool provides status and history monitoring:

```bash
# Show current status
python3 /home/pi/music-player/cli.py status

# Show live dashboard (refreshes every 2 seconds)
python3 /home/pi/music-player/cli.py dashboard

# Show playback history
python3 /home/pi/music-player/cli.py history

# Show last 100 history entries
python3 /home/pi/music-player/cli.py history -n 100
```

### Service Management

```bash
# Start service
sudo systemctl start music-player.service

# Stop service
sudo systemctl stop music-player.service

# Restart service
sudo systemctl restart music-player.service

# View logs
sudo journalctl -u music-player.service -f

# Check status
sudo systemctl status music-player.service
```

## Button Functions

- **Button 1 (Play/Pause)**: Toggle playback
- **Button 2 (Previous)**: Previous track/item
- **Button 3 (Next)**: Next track/item
- **Button 4 (Cycle Source)**: Switch to next configured source

## File Structure

```
/home/pi/music-player/
├── player.py                 # Main daemon entry point
├── player_controller.py      # Main orchestrator
├── buttons.py                # GPIO button handling
├── sources.py                # Source configuration management
├── playback_history.py       # History logging
├── cli.py                    # CLI tool
├── backends/
│   ├── base.py              # Base backend interface
│   ├── youtube_backend.py   # YouTube playback
│   └── spotify_backend.py   # Spotify playback
├── sources.json             # Source configuration (create from .example)
├── state.json               # Current state (auto-generated)
├── history.json             # Playback history (auto-generated)
├── logs/
│   └── player.log           # Application logs
└── music-player.service     # Systemd service file
```

## Troubleshooting

### No audio output
- Check audio configuration: `speaker-test -t sine -f 440 -l 1`
- Verify audio device: `aplay -l`
- Check volume: `alsamixer`

### spotifyd not installed or not working

**If spotifyd is not installed:**
- spotifyd is optional and may not be in default repositories
- Install from source (requires Rust):
  ```bash
  sudo apt install -y cargo rustc libasound2-dev libssl-dev pkg-config
  cargo install spotifyd --locked
  ```
- Or download pre-built binary from: https://github.com/Spotifyd/spotifyd/releases
- Skip spotifyd if you only use YouTube sources

**If spotifyd is installed but not working:**
- Check if spotifyd is running: `systemctl --user status spotifyd`
- Verify credentials in `~/.config/spotifyd/spotifyd.conf`
- Check logs: `journalctl --user -u spotifyd -f`

### YouTube playback issues
- Verify yt-dlp is up to date: `sudo apt update && sudo apt upgrade yt-dlp`
- Test manually: `yt-dlp --get-url "https://www.youtube.com/watch?v=VIDEO_ID"`

### Buttons not responding
- Verify GPIO pins are correct
- Check wiring (buttons should connect GPIO to GND when pressed)
- Test GPIO: `gpio readall` (if installed)
- Check logs: `sudo journalctl -u music-player.service -f`

## License

This project is provided as-is for personal use.

