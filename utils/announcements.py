"""Source announcement using text-to-speech."""
import logging
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Determine base directory (same logic as sources.py)
_SCRIPT_DIR = Path(__file__).parent.absolute()
if _SCRIPT_DIR.name in ("core", "hardware", "utils", "scripts", "backends"):
    _BASE_DIR = _SCRIPT_DIR.parent
elif _SCRIPT_DIR.name == "rodrigo_radio" or (_SCRIPT_DIR / "config" / "sources.json.example").exists():
    _BASE_DIR = _SCRIPT_DIR
else:
    _BASE_DIR = Path("/home/pi/rodrigo_radio")

CACHE_DIR = _BASE_DIR / "data" / "announcements_cache"


def get_cache_path(source_label: str) -> Path:
    """
    Generate cache file path from source label.
    
    Sanitizes the label by converting to lowercase and replacing
    spaces and special characters with underscores.
    
    Args:
        source_label: The label of the source
        
    Returns:
        Path to the cached WAV file
    """
    # Sanitize label: lowercase, replace spaces and special chars with underscores
    sanitized = source_label.lower()
    # Replace spaces and common special characters with underscores
    sanitized = re.sub(r'[^\w\-]', '_', sanitized)
    # Collapse multiple underscores into one
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    # Ensure we have a valid filename
    if not sanitized:
        sanitized = "unknown_source"
    
    return CACHE_DIR / f"{sanitized}.wav"


def ensure_cache_directory() -> Path:
    """
    Ensure the cache directory exists.
    
    Returns:
        Path to the cache directory
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


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


def generate_cached_audio(source_label: str, cache_dir: Path = None) -> bool:
    """
    Generate cached audio file for a source label using Piper TTS.
    
    Args:
        source_label: The label of the source to generate audio for
        cache_dir: Optional cache directory (defaults to CACHE_DIR)
        
    Returns:
        True if audio was successfully generated and cached, False otherwise
    """
    if cache_dir is None:
        cache_dir = ensure_cache_directory()
    
    cache_path = get_cache_path(source_label)
    
    # Check if already cached
    if cache_path.exists() and cache_path.stat().st_size > 0:
        logger.debug(f"Audio already cached for: {source_label}")
        return True
    
    # Get Piper configuration
    piper_cmd, model_file = _get_piper_config()
    if not piper_cmd or not model_file:
        logger.debug(f"Piper TTS not available, cannot cache audio for: {source_label}")
        return False
    
    try:
        # Create temporary files for input and output
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp_input:
            tmp_input.write(source_label)
            tmp_input_path = tmp_input.name
        
        try:
            # Run piper to generate audio
            # Use longer timeout for cache generation (30s) since it runs in background
            result = subprocess.run(
                [piper_cmd, '--model', model_file, '--input_file', tmp_input_path, '--output_file', str(cache_path)],
                capture_output=True,
                timeout=30
            )
            
            if result.returncode == 0 and cache_path.exists() and cache_path.stat().st_size > 0:
                logger.info(f"Cached audio for source: {source_label}")
                return True
            else:
                logger.warning(f"Failed to generate cached audio for: {source_label}")
                if cache_path.exists():
                    cache_path.unlink()
                return False
        finally:
            # Clean up input file
            if os.path.exists(tmp_input_path):
                os.unlink(tmp_input_path)
                
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout generating cached audio for: {source_label}")
        if cache_path.exists():
            cache_path.unlink()
        return False
    except Exception as e:
        logger.warning(f"Error generating cached audio for {source_label}: {e}")
        if cache_path.exists():
            cache_path.unlink()
        return False


def announce_source(source_label: str):
    """
    Announce the source name using text-to-speech.
    
    Priority order:
    1. Cached Piper TTS audio (fastest, instant playback)
    2. Generate Piper TTS on-the-fly (high quality, local)
    3. espeak-ng/espeak (fallback)
    
    Args:
        source_label: The label of the source to announce
    """
    # First, check for cached audio file
    cache_path = get_cache_path(source_label)
    if cache_path.exists() and cache_path.stat().st_size > 0:
        # Play cached audio file (non-blocking)
        subprocess.Popen(
            ['aplay', str(cache_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info(f"Announced source with cached Piper TTS: {source_label}")
        return
    
    # If no cache, try to generate on-the-fly with Piper TTS
    try:
        piper_cmd, model_file = _get_piper_config()
        if not piper_cmd or not model_file:
            raise FileNotFoundError("piper command or model not found")
        
        # Create temporary files for input and output
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp_input:
            tmp_input.write(source_label)
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
                subprocess.Popen(
                    ['aplay', tmp_output_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.info(f"Announced source with Piper TTS: {source_label}")
                # Clean up temp file after a delay
                threading.Timer(2.0, lambda: os.unlink(tmp_output_path) if os.path.exists(tmp_output_path) else None).start()
                return
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
        logger.debug(f"Piper TTS not available: {e}, trying espeak")
    except Exception as e:
        logger.warning(f"Piper TTS error: {e}, trying espeak")
    
    # Fallback to espeak-ng (better than espeak)
    try:
        subprocess.Popen(
            ['espeak-ng', '-s', '150', '-v', 'en', f'{source_label}'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info(f"Announced source with espeak-ng: {source_label}")
    except FileNotFoundError:
        try:
            # Last resort: espeak
            subprocess.Popen(
                ['espeak', '-s', '150', '-v', 'en', f'{source_label}'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info(f"Announced source with espeak: {source_label}")
        except FileNotFoundError:
            logger.debug(f"TTS not available, would announce: {source_label}")
