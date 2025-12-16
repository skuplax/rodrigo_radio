#!/usr/bin/env python3
"""Broadcast maintenance message using Piper TTS (cached voice)."""
import sys
import os
import subprocess
import tempfile
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Determine base directory
_SCRIPT_DIR = Path(__file__).parent.absolute()
if _SCRIPT_DIR.name == "scripts":
    _BASE_DIR = _SCRIPT_DIR.parent
elif (_SCRIPT_DIR.parent / "config" / "sources.json.example").exists():
    _BASE_DIR = _SCRIPT_DIR.parent
else:
    _BASE_DIR = Path("/home/pi/rodrigo_radio")

# Broadcast cache directory
BROADCAST_CACHE_DIR = _BASE_DIR / "data" / "broadcasts"

# Default maintenance message
DEFAULT_MESSAGE = "Please wait, maintenance ongoing by Jonas"


def ensure_broadcast_directory() -> Path:
    """
    Ensure the broadcast cache directory exists.
    
    Returns:
        Path to the broadcast cache directory
    """
    BROADCAST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return BROADCAST_CACHE_DIR


def _get_piper_config():
    """
    Get Piper TTS command and model file paths.
    
    Returns:
        Tuple of (piper_cmd, model_file) or (None, None) if not available
    """
    # Find piper command
    piper_cmd = None
    for path in ['/home/skayflakes/.local/bin/piper', 'piper']:
        if os.path.exists(path) or subprocess.run(['which', path.split('/')[-1]], capture_output=True).returncode == 0:
            piper_cmd = path if os.path.exists(path) else path.split('/')[-1]
            break
    
    if not piper_cmd:
        return None, None
    
    # Find model file
    model_dir = os.path.expanduser("~/.local/share/piper/models")
    model_file = os.path.join(model_dir, "en_US-lessac-medium.onnx")
    
    if not os.path.exists(model_file):
        # Look for any .onnx file in the model directory
        if os.path.exists(model_dir):
            onnx_files = [f for f in os.listdir(model_dir) if f.endswith('.onnx')]
            if onnx_files:
                model_file = os.path.join(model_dir, onnx_files[0])
            else:
                return None, None
        else:
            return None, None
    
    return piper_cmd, model_file


def _get_cache_path(message: str) -> Path:
    """
    Generate cache file path from message text.
    
    Args:
        message: The message text
        
    Returns:
        Path to the cached WAV file
    """
    import re
    # Sanitize message: lowercase, replace spaces and special chars with underscores
    sanitized = message.lower()
    sanitized = re.sub(r'[^\w\-]', '_', sanitized)
    sanitized = re.sub(r'_+', '_', sanitized)
    sanitized = sanitized.strip('_')
    if not sanitized:
        sanitized = "maintenance_message"
    
    return BROADCAST_CACHE_DIR / f"{sanitized}.wav"


def generate_cached_audio(message: str) -> bool:
    """
    Generate cached audio file for a message using Piper TTS.
    
    Args:
        message: The message text to generate audio for
        
    Returns:
        True if audio was successfully generated and cached, False otherwise
    """
    ensure_broadcast_directory()
    
    cache_path = _get_cache_path(message)
    
    # Check if already cached
    if cache_path.exists() and cache_path.stat().st_size > 0:
        logger.debug(f"Audio already cached for message: {message}")
        return True
    
    # Get Piper configuration
    piper_cmd, model_file = _get_piper_config()
    if not piper_cmd or not model_file:
        logger.error(f"Piper TTS not available, cannot generate audio for: {message}")
        return False
    
    try:
        # Create temporary files for input and output
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp_input:
            tmp_input.write(message)
            tmp_input_path = tmp_input.name
        
        try:
            # Run piper to generate audio
            result = subprocess.run(
                [piper_cmd, '--model', model_file, '--input_file', tmp_input_path, '--output_file', str(cache_path)],
                capture_output=True,
                timeout=30
            )
            
            if result.returncode == 0 and cache_path.exists() and cache_path.stat().st_size > 0:
                logger.info(f"Cached audio for message: {message}")
                return True
            else:
                logger.warning(f"Failed to generate cached audio for: {message}")
                if cache_path.exists():
                    cache_path.unlink()
                return False
        finally:
            # Clean up input file
            if os.path.exists(tmp_input_path):
                os.unlink(tmp_input_path)
                
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout generating cached audio for: {message}")
        if cache_path.exists():
            cache_path.unlink()
        return False
    except Exception as e:
        logger.warning(f"Error generating cached audio for {message}: {e}")
        if cache_path.exists():
            cache_path.unlink()
        return False


def play_broadcast_message(message: str = None, blocking: bool = False):
    """
    Play a broadcast message using Piper TTS (cached or generated on-the-fly).
    
    Args:
        message: The message text to broadcast (default: "Please wait, maintenance ongoing by Jonas")
        blocking: If True, wait for playback to complete. If False, play in background (default: False)
    
    Returns:
        True if playback started successfully, False otherwise
    """
    if message is None:
        message = DEFAULT_MESSAGE
    
    ensure_broadcast_directory()
    
    # First, try to use cached audio
    cache_path = _get_cache_path(message)
    if cache_path.exists() and cache_path.stat().st_size > 0:
        # Play cached audio file
        try:
            if blocking:
                result = subprocess.run(
                    ['aplay', str(cache_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                if result.returncode == 0:
                    logger.info(f"Played cached broadcast message: {message}")
                    return True
                else:
                    logger.error(f"Failed to play cached broadcast message")
                    return False
            else:
                subprocess.Popen(
                    ['aplay', str(cache_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.info(f"Playing cached broadcast message: {message}")
                return True
        except FileNotFoundError:
            logger.error("aplay command not found. Please install alsa-utils: sudo apt install alsa-utils")
            return False
        except Exception as e:
            logger.error(f"Error playing cached broadcast message: {e}")
            return False
    
    # If no cache, try to generate on-the-fly with Piper TTS
    try:
        piper_cmd, model_file = _get_piper_config()
        if not piper_cmd or not model_file:
            logger.error("Piper TTS not available and no cached audio found")
            return False
        
        # Create temporary files for input and output
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp_input:
            tmp_input.write(message)
            tmp_input_path = tmp_input.name
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_output:
            tmp_output_path = tmp_output.name
        
        try:
            # Run piper
            result = subprocess.run(
                [piper_cmd, '--model', model_file, '--input_file', tmp_input_path, '--output_file', tmp_output_path],
                capture_output=True,
                timeout=10
            )
            
            # Clean up input file
            if os.path.exists(tmp_input_path):
                os.unlink(tmp_input_path)
            
            if result.returncode == 0 and os.path.exists(tmp_output_path) and os.path.getsize(tmp_output_path) > 0:
                # Play the generated audio
                try:
                    if blocking:
                        play_result = subprocess.run(
                            ['aplay', tmp_output_path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        if play_result.returncode == 0:
                            logger.info(f"Played broadcast message with Piper TTS: {message}")
                            # Try to cache it for next time
                            try:
                                import shutil
                                shutil.copy2(tmp_output_path, cache_path)
                            except Exception:
                                pass
                            # Clean up temp file
                            if os.path.exists(tmp_output_path):
                                os.unlink(tmp_output_path)
                            return True
                        else:
                            if os.path.exists(tmp_output_path):
                                os.unlink(tmp_output_path)
                            return False
                    else:
                        subprocess.Popen(
                            ['aplay', tmp_output_path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        logger.info(f"Playing broadcast message with Piper TTS: {message}")
                        # Try to cache it for next time (in background)
                        import threading
                        def cache_and_cleanup():
                            import time
                            time.sleep(2.0)  # Wait for aplay to read the file
                            try:
                                import shutil
                                shutil.copy2(tmp_output_path, cache_path)
                            except Exception:
                                pass
                            if os.path.exists(tmp_output_path):
                                os.unlink(tmp_output_path)
                        threading.Thread(target=cache_and_cleanup, daemon=True).start()
                        return True
                except FileNotFoundError:
                    logger.error("aplay command not found. Please install alsa-utils: sudo apt install alsa-utils")
                    if os.path.exists(tmp_output_path):
                        os.unlink(tmp_output_path)
                    return False
                except Exception as e:
                    logger.error(f"Error playing generated audio: {e}")
                    if os.path.exists(tmp_output_path):
                        os.unlink(tmp_output_path)
                    return False
            else:
                if os.path.exists(tmp_output_path):
                    os.unlink(tmp_output_path)
                raise subprocess.CalledProcessError(result.returncode, piper_cmd, result.stderr)
        except Exception as e:
            # Clean up on error
            if os.path.exists(tmp_input_path):
                os.unlink(tmp_input_path)
            if os.path.exists(tmp_output_path):
                os.unlink(tmp_output_path)
            raise
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error(f"Piper TTS error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error generating broadcast message: {e}")
        return False


def main():
    """Main entry point for the broadcast script."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Broadcast maintenance message using Piper TTS (cached voice)"
    )
    parser.add_argument(
        '--message',
        '-m',
        default=None,
        help=f'Message text to broadcast (default: "{DEFAULT_MESSAGE}")'
    )
    parser.add_argument(
        '--blocking',
        '-b',
        action='store_true',
        help='Wait for playback to complete (default: non-blocking)'
    )
    parser.add_argument(
        '--generate-cache',
        '-g',
        action='store_true',
        help='Generate and cache the audio file without playing it'
    )
    
    args = parser.parse_args()
    
    message = args.message if args.message else DEFAULT_MESSAGE
    
    if args.generate_cache:
        # Just generate cache without playing
        success = generate_cached_audio(message)
        if success:
            cache_path = _get_cache_path(message)
            logger.info(f"Generated cached audio at: {cache_path}")
        sys.exit(0 if success else 1)
    else:
        # Play the message
        success = play_broadcast_message(message, blocking=args.blocking)
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
