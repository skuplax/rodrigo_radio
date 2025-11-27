"""Source announcement using text-to-speech."""
import logging
import os
import subprocess
import tempfile
import threading

logger = logging.getLogger(__name__)


def announce_source(source_label: str):
    """
    Announce the source name using text-to-speech.
    
    Priority order:
    1. Piper TTS (high quality, local)
    2. espeak-ng/espeak (fallback)
    
    Args:
        source_label: The label of the source to announce
    """
    # Try Piper TTS (much better quality than espeak)
    try:
        # Find piper command
        piper_cmd = None
        for path in ['/home/skayflakes/.local/bin/piper', 'piper']:
            if os.path.exists(path) or subprocess.run(['which', path.split('/')[-1]], capture_output=True).returncode == 0:
                piper_cmd = path if os.path.exists(path) else path.split('/')[-1]
                break
        
        if not piper_cmd:
            raise FileNotFoundError("piper command not found")
        
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
                    raise FileNotFoundError(f"No .onnx model files found in {model_dir}")
            else:
                raise FileNotFoundError(f"Model directory not found: {model_dir}")
        
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
