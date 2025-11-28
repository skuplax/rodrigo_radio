#!/bin/bash
# Installation script for Raspberry Pi Music Player
# This script handles both system package installation (requires sudo) and user setup

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory and target directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="/home/pi/rodrigo_radio"
SERVICE_FILE="rodrigo_radio.service"

# Functions
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        return 1
    fi
    return 0
}

# Main installation function
main() {
    echo ""
    echo "=========================================="
    echo "Raspberry Pi Music Player Installation"
    echo "=========================================="
    echo ""

    # Check if running as root for system packages
    if [ "$EUID" -eq 0 ]; then
        print_info "Running as root - installing system packages..."
        
        apt update
        
        # Install required packages
        print_info "Installing required packages..."
        apt install -y \
            yt-dlp \
            mpv \
            python3-gpiozero \
            python3-dbus \
            python3-pip \
            python3-venv
        
        # Try to install spotifyd (optional - may not be in repos)
        print_info "Attempting to install spotifyd (optional for Spotify support)..."
        if apt install -y spotifyd 2>/dev/null; then
            print_info "spotifyd installed successfully from repository"
        else
            print_warn "spotifyd not available in default repositories"
            echo ""
            print_info "spotifyd is optional - only needed if you want to use Spotify sources"
            print_info "You can install it later using one of these methods:"
            echo ""
            echo "  Option 1: Install from source (requires Rust):"
            echo "    sudo apt install -y cargo rustc libasound2-dev libssl-dev pkg-config"
            echo "    cargo install spotifyd --locked"
            echo ""
            echo "  Option 2: Download pre-built binary:"
            echo "    Visit: https://github.com/Spotifyd/spotifyd/releases"
            echo ""
            echo "  Option 3: Skip if you only use YouTube sources (recommended for now)"
            echo ""
            print_info "Continuing installation without spotifyd..."
        fi
        
        print_info "System packages installed successfully!"
        echo ""
        print_warn "Please run the rest of the installation as the 'pi' user:"
        echo "  cd $TARGET_DIR"
        echo "  ./install.sh"
        exit 0
    fi

    # Check if we're the pi user (or allow override)
    if [ "$USER" != "pi" ]; then
        print_warn "Not running as 'pi' user. Some paths may be incorrect."
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    print_info "Installing Python packages..."
    if ! pip3 install --user gpiozero; then
        print_error "Failed to install Python packages"
        exit 1
    fi

    echo ""
    print_info "Setting up project directory..."

    # Copy files to target directory if not already there
    if [ "$SCRIPT_DIR" != "$TARGET_DIR" ]; then
        print_info "Copying files to $TARGET_DIR..."
        if [ ! -d "$TARGET_DIR" ]; then
            sudo mkdir -p "$TARGET_DIR"
        fi
        sudo cp -r "$SCRIPT_DIR"/* "$TARGET_DIR/" 2>/dev/null || {
            print_error "Failed to copy files. You may need to run: sudo chown -R $USER:$USER $TARGET_DIR"
            exit 1
        }
        sudo chown -R "$USER:$USER" "$TARGET_DIR"
        cd "$TARGET_DIR"
    else
        print_info "Files already in target directory."
    fi

    # Make scripts executable
    print_info "Making scripts executable..."
    chmod +x main.py cli.py install.sh 2>/dev/null || true

    # Create necessary directories
    print_info "Creating necessary directories..."
    mkdir -p logs
    mkdir -p ~/.config/spotifyd
    mkdir -p ~/.cache/spotifyd

    # Create config directory if it doesn't exist
    mkdir -p config
    
    # Create sources.json if it doesn't exist
    if [ ! -f config/sources.json ]; then
        if [ -f config/sources.json.example ]; then
            print_info "Creating sources.json from example..."
            cp config/sources.json.example config/sources.json
            print_warn "Please edit config/sources.json with your source configurations."
        else
            print_warn "sources.json.example not found in config/ directory"
        fi
    else
        print_info "config/sources.json already exists, skipping..."
    fi

    # Create spotifyd config if it doesn't exist
    if [ ! -f ~/.config/spotifyd/spotifyd.conf ]; then
        if [ -f config/spotifyd.conf.example ]; then
            print_info "Creating spotifyd.conf from example..."
            cp config/spotifyd.conf.example ~/.config/spotifyd/spotifyd.conf
            print_warn "Please edit ~/.config/spotifyd/spotifyd.conf with your Spotify credentials."
        fi
    else
        print_info "spotifyd.conf already exists, skipping..."
    fi
    
    # Create data directory for runtime files
    mkdir -p data

    # Install systemd service
    echo ""
    print_info "Installing systemd service..."
    
    if [ ! -f "$SERVICE_FILE" ]; then
        print_error "Service file $SERVICE_FILE not found!"
        exit 1
    fi

    # Copy service file
    sudo cp "$SERVICE_FILE" /etc/systemd/system/
    sudo systemctl daemon-reload
    
    print_info "Systemd service installed successfully!"
    
    # Ask if user wants to enable and start the service
    echo ""
    read -p "Enable and start the rodrigo_radio service now? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo systemctl enable rodrigo_radio.service
        print_info "Service enabled to start on boot."
        
        read -p "Start the service now? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo systemctl start rodrigo_radio.service
            sleep 2
            if sudo systemctl is-active --quiet rodrigo_radio.service; then
                print_info "Service started successfully!"
            else
                print_error "Service failed to start. Check logs with: sudo journalctl -u rodrigo_radio.service -n 50"
            fi
        fi
    else
        print_info "Service installed but not enabled. Enable it later with:"
        echo "  sudo systemctl enable rodrigo_radio.service"
        echo "  sudo systemctl start rodrigo_radio.service"
    fi

    # Check if spotifyd should be started
    echo ""
    if [ -f ~/.config/spotifyd/spotifyd.conf ]; then
        read -p "Start spotifyd service (user service)? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            systemctl --user enable spotifyd 2>/dev/null || true
            systemctl --user start spotifyd 2>/dev/null || true
            print_info "spotifyd service configured."
        fi
    fi

    # Summary
    echo ""
    echo "=========================================="
    print_info "Installation complete!"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "1. Edit $TARGET_DIR/config/sources.json with your sources"
    if [ ! -f ~/.config/spotifyd/spotifyd.conf ] || grep -q "your_spotify_username" ~/.config/spotifyd/spotifyd.conf 2>/dev/null; then
        echo "2. Edit ~/.config/spotifyd/spotifyd.conf with your Spotify credentials (if using Spotify)"
    fi
    echo ""
    echo "Service management:"
    echo "  Start:   sudo systemctl start rodrigo_radio.service"
    echo "  Stop:    sudo systemctl stop rodrigo_radio.service"
    echo "  Restart: sudo systemctl restart rodrigo_radio.service"
    echo "  Status:  sudo systemctl status rodrigo_radio.service"
    echo "  Logs:    sudo journalctl -u rodrigo_radio.service -f"
    echo ""
    echo "CLI tool:"
    echo "  Status:  python3 $TARGET_DIR/cli.py status"
    echo "  History: python3 $TARGET_DIR/cli.py history"
    echo "  Dashboard: python3 $TARGET_DIR/cli.py dashboard"
    echo ""
}

# Run main function
main "$@"
