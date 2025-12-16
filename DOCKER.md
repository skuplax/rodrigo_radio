# Docker Setup for Rodrigo Radio

This guide explains how to run Rodrigo Radio in a Docker container for development and testing.

## Prerequisites

- Docker and Docker Compose installed
- For Raspberry Pi: Docker should support ARM architecture
- For development: Docker on x86_64/amd64 works fine (hardware features will be disabled)

## Quick Start

### 1. Build the Docker Image

```bash
docker-compose build
```

Or build directly:

```bash
docker build -t rodrigo-radio .
```

### 2. Set Up Configuration

Before running, you need to set up your configuration files:

```bash
# Copy example config files
cp config/sources.json.example config/sources.json
cp config/spotify_api_config.json.example config/spotify_api_config.json  # If using Spotify

# Edit with your settings
nano config/sources.json
```

### 3. Set Up Environment Variables

Create a `.env` file in the project root (optional):

```bash
# Supabase configuration
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# Timezone
TZ=America/New_York
```

### 4. Run the Container

**Development mode (without hardware):**

```bash
docker-compose up
```

**Production mode (with hardware access on Raspberry Pi):**

First, edit `docker-compose.yml` and uncomment the hardware access lines:

```yaml
privileged: true
devices:
  - /dev/gpiomem:/dev/gpiomem
  - /dev/snd:/dev/snd
```

Then run:

```bash
docker-compose up -d
```

## Development Workflow

### Live Code Editing

The `docker-compose.yml` mounts the current directory, so code changes are reflected immediately. However, you may need to restart the container for some changes:

```bash
docker-compose restart
```

### Viewing Logs

```bash
# Follow logs
docker-compose logs -f

# View last 100 lines
docker-compose logs --tail=100
```

### Running CLI Commands

```bash
# Status
docker-compose exec rodrigo-radio python3 cli.py status

# Dashboard
docker-compose exec rodrigo-radio python3 cli.py dashboard

# History
docker-compose exec rodrigo-radio python3 cli.py history
```

### Interactive Shell

```bash
docker-compose exec rodrigo-radio bash
```

## Hardware Access (Raspberry Pi Only)

For production use on Raspberry Pi with actual hardware:

1. **GPIO Access**: The container needs access to `/dev/gpiomem` or run in privileged mode
2. **Audio Access**: The container needs access to `/dev/snd` for ALSA audio

Edit `docker-compose.yml`:

```yaml
services:
  rodrigo-radio:
    privileged: true  # Required for GPIO access
    devices:
      - /dev/gpiomem:/dev/gpiomem
      - /dev/snd:/dev/snd
```

**Note**: Running in privileged mode has security implications. For production, consider using more granular device access.

## Development Without Hardware

For development and testing on a non-Raspberry Pi system:

- GPIO operations will fail gracefully (the code handles missing hardware)
- Audio can be tested using PulseAudio passthrough or by mocking
- All other features (Spotify, YouTube, Supabase logging) work normally

## Building for Different Architectures

### For Raspberry Pi (ARM)

```bash
docker buildx build --platform linux/arm/v7 -t rodrigo-radio:arm .
```

### For x86_64 (Development)

```bash
docker buildx build --platform linux/amd64 -t rodrigo-radio:amd64 .
```

## Troubleshooting

### Container won't start

Check logs:
```bash
docker-compose logs rodrigo-radio
```

### GPIO not working

- Ensure you're running on Raspberry Pi
- Check that `/dev/gpiomem` exists: `ls -l /dev/gpiomem`
- Try running with `privileged: true` in docker-compose.yml

### Audio not working

- Check ALSA devices: `docker-compose exec rodrigo-radio aplay -l`
- Ensure audio devices are mounted: `/dev/snd` in docker-compose.yml
- For development, you may need to configure PulseAudio passthrough

### Config file not found

- Ensure `config/sources.json` exists (copy from example)
- Check volume mounts in docker-compose.yml
- Verify file permissions

### Supabase connection issues

- Check `.env` file has correct `SUPABASE_URL` and `SUPABASE_KEY`
- Verify network connectivity from container
- Check Supabase logs for connection errors

## Stopping the Container

```bash
# Stop gracefully
docker-compose stop

# Stop and remove
docker-compose down

# Stop, remove, and clean volumes
docker-compose down -v
```

## Production Deployment

For production on Raspberry Pi:

1. Build the image on the Pi or use buildx for cross-compilation
2. Use `docker-compose.prod.yml` (create this) with production settings
3. Set up proper logging and monitoring
4. Configure automatic restarts
5. Set up health checks

Example `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  rodrigo-radio:
    build: .
    restart: always
    privileged: true
    devices:
      - /dev/gpiomem:/dev/gpiomem
      - /dev/snd:/dev/snd
    volumes:
      - ./config:/app/config:ro
      - ./data:/app/data
      - ./logs:/app/logs
    env_file:
      - .env
```

Run with:
```bash
docker-compose -f docker-compose.prod.yml up -d
```
