# Dockerfile for Rodrigo Radio
# Supports both ARM (Raspberry Pi) and x86_64 (development)
# Multi-architecture: Use buildx for cross-platform builds

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    yt-dlp \
    mpv \
    alsa-utils \
    dbus \
    && rm -rf /var/lib/apt/lists/*

# Install Python system packages (gpiozero needs these)
# Note: gpiozero may not work on non-ARM systems, but the code handles this gracefully
RUN apt-get update && apt-get install -y \
    python3-gpiozero \
    python3-dbus \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs data config announcements

# Make scripts executable
RUN chmod +x main.py cli.py install.sh scripts/*.py 2>/dev/null || true

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default command (can be overridden)
CMD ["python3", "main.py"]


