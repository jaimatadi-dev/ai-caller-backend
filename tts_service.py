import os
import logging
import uuid
from typing import Optional
import soundfile as sf
import urllib.request

logger = logging.getLogger(__name__)

class TTSService:
    def __init__(self):
        # Setup output directory for WAV files
        self.output_dir = os.path.join(os.path.dirname(__file__), 'audio_files')
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.kokoro = None
        
        # Determine paths relative to the project root
        project_root = os.path.dirname(__file__)
        model_path = os.path.join(project_root, "kokoro-v0_19.onnx")
        voices_path = os.path.join(project_root, "voices.bin")
        
        # Download logic
        model_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx"
        voices_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin"
        
        try:
            if not os.path.exists(model_path):
                logger.info(f"Downloading Kokoro model from {model_url}...")
                urllib.request.urlretrieve(model_url, model_path)
            
            if not os.path.exists(voices_path):
                logger.info(f"Downloading Kokoro voices from {voices_url}...")
                urllib.request.urlretrieve(voices_url, voices_path)
            
            from kokoro_onnx import Kokoro
            self.kokoro = Kokoro(model_path, voices_path)
            logger.info("Kokoro model loaded successfully")
            
        except ImportError:
            logger.error("kokoro-onnx package not installed.")
        except Exception as e:
            logger.error(f"Error initializing Kokoro TTS: {e}")

    def text_to_speech(self, text: str) -> Optional[str]:
        """Converts text to speech and returns the file path."""
        try:
            filename = f"tts_{uuid.uuid4().hex}.wav"
            filepath = os.path.join(self.output_dir, filename)
            
            if self.kokoro:
                logger.info(f"Generating TTS for text: '{text[:30]}...'")
                samples, sample_rate = self.kokoro.create(
                    text, voice="af_sarah", speed=1.0, lang="en"
                )
                sf.write(filepath, samples, sample_rate)
                logger.info(f"Generated TTS file: {filepath}")
                return filepath
            else:
                logger.error("TTS generation failed: Kokoro model is not loaded.")
                return None
            
        except Exception as e:
            logger.error(f"TTS generation failed: {e}", exc_info=True)
            return None
