"""GPIO button handling with debouncing."""
import logging
from typing import Callable, Optional
from gpiozero import Button
from signal import pause

logger = logging.getLogger(__name__)

# Default GPIO pins for buttons
DEFAULT_PINS = {
    'play_pause': 17,
    'previous': 27,
    'next': 22,
    'cycle_source': 23
}


class ButtonHandler:
    """Handles GPIO button inputs with debouncing."""
    
    def __init__(self, pins: dict = None, bounce_time: float = 0.1):
        """
        Initialize button handler.
        
        Args:
            pins: Dictionary mapping button names to GPIO pins.
                  Defaults to DEFAULT_PINS if not provided.
            bounce_time: Debounce time in seconds (default: 0.1)
        """
        self.pins = pins or DEFAULT_PINS
        self.bounce_time = bounce_time
        self.buttons = {}
        self.callbacks = {}
        self._setup_buttons()
    
    def _setup_buttons(self):
        """Set up GPIO buttons with pull-up resistors and debouncing.
        
        For normally open (NO) buttons that close to GND when pressed:
        - pull_up=True: Use internal pull-up resistor (keeps pin HIGH when not pressed)
        - When button is pressed: pin goes LOW (button connects GPIO to GND)
        - gpiozero automatically detects LOW as "pressed" when pull_up=True
        """
        try:
            for name, pin in self.pins.items():
                button = Button(
                    pin,
                    pull_up=True,  # For NO buttons: HIGH when not pressed, LOW when pressed (closes to GND)
                    bounce_time=self.bounce_time
                )
                self.buttons[name] = button
                logger.info(f"Configured button '{name}' on GPIO {pin} (NO button, closes to GND when pressed)")
        except Exception as e:
            logger.error(f"Error setting up buttons: {e}")
            raise
    
    def register_callback(self, button_name: str, callback: Callable):
        """
        Register a callback for a button press.
        
        Args:
            button_name: Name of the button (e.g., 'play_pause')
            callback: Function to call when button is pressed
        """
        if button_name not in self.buttons:
            logger.warning(f"Button '{button_name}' not found")
            return
        
        # Remove existing callback if any
        if button_name in self.callbacks:
            self.buttons[button_name].when_pressed = None
        
        # Set new callback
        def wrapped_callback():
            logger.info(f"Button '{button_name}' pressed - invoking callback")
            try:
                callback()
                logger.debug(f"Button '{button_name}' callback completed successfully")
            except Exception as e:
                logger.error(f"Error in button callback for '{button_name}': {e}", exc_info=True)
        
        self.buttons[button_name].when_pressed = wrapped_callback
        self.callbacks[button_name] = callback
        logger.debug(f"Registered callback for button '{button_name}'")
    
    def wait(self):
        """Wait for button presses (blocks forever)."""
        logger.info("Button handler waiting for input...")
        pause()

