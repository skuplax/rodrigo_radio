#!/usr/bin/env python3
"""Main daemon entry point for the music player."""
import sys
import signal
import logging
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # python-dotenv not required, but helpful

from core.player_controller import PlayerController

# Configure logging - use script directory
SCRIPT_DIR = Path(__file__).parent.absolute()
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "player.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
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
        # Initialize controller with paths relative to script directory
        sources_file = SCRIPT_DIR / "config" / "sources.json"
        state_file = SCRIPT_DIR / "data" / "state.json"
        
        # Optional: Configure rotary encoder pins
        # Set to None to disable rotary encoder
        # Example: encoder_pins = {'clk': 5, 'dt': 6, 'sw': 13, 'volume_step': 2}
        encoder_pins = {
            'clk': 5, 
            'dt': 6, 
            'sw': None, 
            'volume_step': 2,  # KY-040 on GPIO 5 (CLK) and 6 (DT)
            # Time-based volume limiting dB offsets:
            'time_limit_day_db': 0.0,        # Day hours (9am-5pm)
            'time_limit_evening_db': -6.0,   # Evening transition (6pm-7pm, 8am-9am)
            'time_limit_night_db': -12.0     # Night hours (7pm-7am)
        }
        
        controller = PlayerController(
            sources_file=sources_file,
            state_file=state_file,
            encoder_pins=encoder_pins
        )
        
        # Log startup event
        controller.history.log_config_event('startup', 
                                           sources_file=str(sources_file),
                                           state_file=str(state_file))
        
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

