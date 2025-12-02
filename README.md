# Raspberry Pi Music Player

A headless music and news player for Raspberry Pi controlled by physical buttons.

## Features

- **4-button control**: Play/Pause, Previous, Next, Cycle Source
- **Rotary encoder volume control**: Optional digital rotary encoder for system audio volume
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
- **Optional**: Digital rotary encoder (KY-040 or similar) for volume control

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

**Note:** yt-dlp is required for mpv to play YouTube URLs (mpv uses it internally). However, we use fast RSS feeds (~100-200ms) for channel video discovery instead of calling yt-dlp directly (which took 5-11 seconds).

**Note:** `raspotify` is required for Spotify sources. It will be installed automatically (see Spotify Setup section below).

### Python Packages

```bash
pip3 install --user --break-system-packages gpiozero spotipy
```

## Installation

### Automated Installation (Recommended)

1. **Navigate to the project directory**:
   ```bash
   cd /home/pi/rodrigo_radio
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

4. **Set up Spotify** (if using Spotify sources):
   - The install script will prompt you to set up Spotify Web API authentication
   - You can skip this and set it up later if needed
   - See the "Spotify Setup" section below for detailed instructions

5. **Configure your sources**:
   ```bash
   nano /home/pi/rodrigo_radio/sources.json
   ```
   Edit the file with your Spotify playlist IDs and YouTube channel/playlist IDs.

### Manual Installation

If you prefer to install manually:

1. **Install system packages**:
   ```bash
   sudo apt update
   sudo apt install -y yt-dlp mpv python3-gpiozero python3-pip
   ```
   
   **Note:** yt-dlp is required for mpv to play YouTube URLs (mpv uses it internally). We use RSS feeds for fast channel video discovery instead of calling yt-dlp directly.

2. **Install raspotify** (for Spotify support):
   ```bash
   curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
   ```

3. **Install Python packages**:
   ```bash
   pip3 install --user --break-system-packages gpiozero spotipy
   ```

3. **Clone or copy this directory to `/home/pi/rodrigo_radio`**

4. **Make scripts executable**:
   ```bash
   chmod +x /home/pi/rodrigo_radio/main.py
   chmod +x /home/pi/rodrigo_radio/cli.py
   ```

5. **Configure sources**:
   ```bash
   cp /home/pi/rodrigo_radio/sources.json.example /home/pi/rodrigo_radio/sources.json
   nano /home/pi/rodrigo_radio/sources.json
   ```

6. **Set up Spotify** (if using Spotify sources):
   See the "Spotify Setup" section below.

7. **Install systemd service**:
   ```bash
   sudo cp /home/pi/rodrigo_radio/rodrigo_radio.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable rodrigo_radio.service
   sudo systemctl start rodrigo_radio.service
   ```

## Configuration

### Button GPIO Pins

Default pins (can be changed in `buttons.py` or `player_controller.py`):
- Button 1 (Play/Pause): GPIO 17
- Button 2 (Previous): GPIO 27
- Button 3 (Next): GPIO 22
- Button 4 (Cycle Source): GPIO 23

### Rotary Encoder Configuration (Optional)

To add volume control with a digital rotary encoder (e.g., KY-040):

1. **Hardware Wiring**:
   - **CLK** (Clock) → GPIO pin (e.g., GPIO 5)
   - **DT** (Data) → GPIO pin (e.g., GPIO 6)
   - **SW** (Switch/Button) → GPIO pin (e.g., GPIO 13) - optional, for mute toggle
   - **+** → 3.3V
   - **GND** → Ground

2. **Software Configuration**: Edit `/home/skayflakes/rodrigo_radio/main.py`:
   ```python
   encoder_pins = {'clk': 5, 'dt': 6, 'sw': 13, 'volume_step': 2}
   ```
   - `clk`: GPIO pin for CLK signal (required)
   - `dt`: GPIO pin for DT signal (required)
   - `sw`: GPIO pin for switch/button (optional, for mute toggle)
   - `volume_step`: Volume change per encoder step in percent (default: 2)

3. **Test the encoder**: Before enabling in the service, test it manually or check logs:
   ```bash
   sudo systemctl stop rodrigo_radio.service
   # Test by running the player and rotating the encoder
   # Check logs: sudo journalctl -u rodrigo_radio.service -f
   ```

The encoder controls system audio volume using ALSA mixer (`amixer`). Rotate clockwise to increase volume, counter-clockwise to decrease. Press the switch (if connected) to toggle mute/unmute.

### Source Announcements (Text-to-Speech)

When cycling between sources, the player can announce the source name. The system tries multiple methods in order of quality:

1. **Pre-recorded Audio Files** (Best Quality): Place audio files in the `announcements/` directory named after your source labels (e.g., `music_-_80s_love_songs.wav`). Supported formats: WAV, MP3, OGG.

2. **Piper TTS** (High Quality, Local): Much better than espeak. Install with:
   ```bash
   pip3 install --user --break-system-packages piper-tts
   ```
   Models will be downloaded automatically on first use. This provides natural-sounding speech without internet.

3. **espeak-ng/espeak** (Fallback): Basic TTS, already installed on most Raspberry Pi systems.

**To use pre-recorded audio:**
```bash
mkdir -p /home/pi/rodrigo_radio/announcements
# Record or place your audio files here
# Filename should match source label (spaces -> underscores, lowercase)
# Example: "Music - 80s Love Songs" -> "music_-_80s_love_songs.wav"
```

**To use Piper TTS:**
```bash
pip3 install --user --break-system-packages piper-tts
# First run will download a model (~50MB)
```

### Sources Configuration

Edit `/home/pi/rodrigo_radio/sources.json`:

- **Spotify Playlist**: Requires `playlist_id` (full URI or just ID)
- **YouTube Channel**: Requires `channel_id` (starts with `UC`)
  - Uses RSS feeds for fast video discovery
  - Automatically advances to next video when current ends
  - Seamlessly checks for live streams in background
- **YouTube Playlist**: Requires `playlist_id` (starts with `PL`)
  - Note: Playlists still require yt-dlp (playlists don't have easy RSS access)

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

### Spotify Setup

This player uses **raspotify** as the Spotify Connect client and the **Spotify Web API** for programmatic control. This allows independent control without needing the Spotify mobile/desktop app.

#### 1. Install and Configure Raspotify

Raspotify should already be installed. Verify it's running:
```bash
sudo systemctl status raspotify
```

Configure raspotify for 3.5mm jack audio (already configured if you used the automated setup):
```bash
sudo nano /etc/raspotify/conf
```

Ensure these settings are present:
```bash
DEVICE_NAME="Raspberry Pi"
BACKEND_ARGS="--backend alsa --device sysdefault:Headphones"
BITRATE="160"
```

Restart raspotify:
```bash
sudo systemctl restart raspotify
```

#### 2. Set Up Spotify Web API

To enable programmatic control, you need to set up OAuth authentication. **The install script will prompt you to do this during installation**, but you can also set it up manually:

**Option A: During Installation (Recommended)**
- When running `./install.sh`, you'll be prompted: "Set up Spotify Web API authentication now? (y/N)"
- If you choose yes, the OAuth setup script will run automatically
- Make sure you have created a Spotify app first (see step 1 below)

**Option B: Manual Setup**
1. **Create a Spotify App**:
   - Go to https://developer.spotify.com/dashboard
   - Click "Create app"
   - Fill in app details (name, description)
   - Add redirect URI: `http://127.0.0.1:8888/callback`
   - Save and note your **Client ID** and **Client Secret**

2. **Run the OAuth Setup Script**:
   ```bash
   cd /home/pi/rodrigo_radio
   python3 scripts/spotify_oauth_setup.py
   ```
   
   Follow the prompts:
   - Enter your Client ID and Client Secret
   - Authorize the app in your browser (the script will open it automatically)
   - The script will capture the authorization callback automatically
   
   The script will save your credentials to `config/spotify_api_config.json`.

3. **Verify Setup**:
   The script will test the connection. If successful, you're ready to use Spotify sources!

**Note**: You need a **Spotify Premium** account for this to work.

## Usage

### CLI Tool

The CLI tool provides status and history monitoring:

```bash
# Show current status
python3 /home/pi/rodrigo_radio/cli.py status

# Show live dashboard (refreshes every 2 seconds)
python3 /home/pi/rodrigo_radio/cli.py dashboard

# Show playback history
python3 /home/pi/rodrigo_radio/cli.py history

# Show last 100 history entries
python3 /home/pi/rodrigo_radio/cli.py history -n 100
```

### Service Management

```bash
# Start service
sudo systemctl start rodrigo_radio.service

# Stop service
sudo systemctl stop rodrigo_radio.service

# Restart service
sudo systemctl restart rodrigo_radio.service

# View logs
sudo journalctl -u rodrigo_radio.service -f

# Check status
sudo systemctl status rodrigo_radio.service
```

## Button Functions

- **Button 1 (Play/Pause)**: Toggle playback
- **Button 2 (Previous)**: Previous track/item
- **Button 3 (Next)**: Next track/item
- **Button 4 (Cycle Source)**: Switch to next configured source

## Rotary Encoder Functions (if enabled)

- **Rotate Clockwise**: Increase system volume
- **Rotate Counter-clockwise**: Decrease system volume
- **Press Switch** (if connected): Toggle mute/unmute

## File Structure

```
/home/pi/rodrigo_radio/
├── main.py                   # Main daemon entry point
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
└── rodrigo_radio.service     # Systemd service file
```

## Troubleshooting

### No audio output
- Check audio configuration: `speaker-test -t sine -f 440 -l 1`
- Verify audio device: `aplay -l`
- Check volume: `alsamixer`

### Spotify/Raspotify Issues

**If raspotify is not running:**
- Check status: `sudo systemctl status raspotify`
- Start service: `sudo systemctl start raspotify`
- Check logs: `sudo journalctl -u raspotify -f`

**If Spotify Web API authentication fails:**
- Verify config file exists: `ls -la ~/rodrigo_radio/config/spotify_api_config.json`
- Re-run OAuth setup: `python3 ~/rodrigo_radio/scripts/spotify_oauth_setup.py`
- Or re-run the install script and choose to set up Spotify when prompted
- Check that redirect URI matches in Spotify app settings: `http://127.0.0.1:8888/callback`

**If device not found:**
- Make sure raspotify is running and visible in Spotify app
- Connect to "Raspberry Pi" device once from Spotify app to register it
- Check device name matches in `/etc/raspotify/conf`

**If playback doesn't start:**
- Verify you have Spotify Premium (required for Web API)
- Check that the playlist/album/track URI is correct
- Review logs: `sudo journalctl -u raspotify -f`

### YouTube playback issues
- **Channels:** Uses RSS feeds for fast video discovery (~100-200ms vs 5-11 seconds with yt-dlp)
- **Auto-advance:** Videos automatically advance to the next video when current ends
- **Playlists:** Still requires yt-dlp (playlists don't have easy RSS access)
- If channel RSS feed fails, check network connectivity
- Test RSS feed manually: `curl "https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID"`

### Buttons not responding
- Verify GPIO pins are correct
- Check wiring (buttons should connect GPIO to GND when pressed)
- Test GPIO: `gpio readall` (if installed)
- Check logs: `sudo journalctl -u rodrigo_radio.service -f`

## License

This project is provided as-is for personal use.

