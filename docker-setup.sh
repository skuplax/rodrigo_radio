#!/bin/bash
# Quick setup script for Docker environment

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Rodrigo Radio Docker Setup"
echo "=========================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "Error: Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p config data logs announcements

# Set up config files if they don't exist
if [ ! -f config/sources.json ]; then
    if [ -f config/sources.json.example ]; then
        echo "Creating config/sources.json from example..."
        cp config/sources.json.example config/sources.json
        echo "⚠️  Please edit config/sources.json with your source configurations."
    else
        echo "⚠️  Warning: config/sources.json.example not found. You'll need to create config/sources.json manually."
    fi
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file template..."
    cat > .env <<EOF
# Supabase Configuration (optional, but recommended)
# SUPABASE_URL=your_supabase_url_here
# SUPABASE_KEY=your_supabase_key_here

# Timezone
TZ=America/New_York

# Add other environment variables as needed
EOF
    echo "⚠️  Please edit .env file with your configuration (especially Supabase if using logging)."
fi

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit config/sources.json with your sources"
echo "2. Edit .env file with your Supabase credentials (if using)"
echo "3. Build the Docker image:"
echo "   docker-compose build"
echo ""
echo "4. Run in development mode:"
echo "   docker-compose up"
echo ""
echo "5. Or run in production mode (Raspberry Pi with hardware):"
echo "   docker-compose -f docker-compose.prod.yml up -d"
echo ""
echo "For more details, see DOCKER.md"


