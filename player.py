#!/usr/bin/env python3
"""Main daemon entry point for the music player."""
import sys
import signal
import logging
from pathlib import Path
from player_controller import PlayerController

# Configure logging
LOG_DIR = Path("/home/pi/music-player/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "player.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Global controller instance
controller: PlayerController = None


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, shutting down...")
    if controller:
        controller.shutdown()
    sys.exit(0)


def main():
    """Main entry point."""
    global controller
    
    logger.info("Starting music player daemon...")
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Initialize controller
        controller = PlayerController()
        
        # Run (blocks forever)
        controller.run()
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if controller:
            controller.shutdown()


if __name__ == '__main__':
    main()

