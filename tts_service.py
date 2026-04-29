import os
import logging
import uuid
from typing import Optional
import soundfile as sf
import numpy as np

logger = logging.getLogger(__name__)

class TTSService:
    def __init__(self):
        # Setup output directory for WAV files
        self.output_dir = os.path.join(os.path.dirname(__file__), 'audio_files')
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.is_loaded = False
        self.kokoro = None
        
        try:
            from kokoro_onnx import Kokoro
            model_path = os.path.join(os.path.dirname(__file__), "kokoro-v0_19.onnx")
            voices_path = os.path.join(os.path.dirname(__file__), "voices.bin")
            
            # Load kokoro ONNX model locally if files exist
            if os.path.exists(model_path) and os.path.exists(voices_path):
                self.kokoro = Kokoro(model_path, voices_path)
                self.is_loaded = True
                logger.info("Kokoro ONNX TTS model loaded successfully.")
            else:
                logger.warning(f"Kokoro model files not found at {model_path}. Using mock TTS for development.")
        except ImportError:
            logger.warning("kokoro-onnx package not installed. Using mock TTS.")
        except Exception as e:
            logger.error(f"Error loading Kokoro TTS: {e}")

    def text_to_speech(self, text: str) -> Optional[str]:
        """Converts text to speech and returns the file path."""
        try:
            filename = f"tts_{uuid.uuid4().hex}.wav"
            filepath = os.path.join(self.output_dir, filename)
            
            if self.is_loaded and self.kokoro:
                logger.info(f"Generating TTS for text: '{text[:30]}...' -> {filepath}")
                samples, sample_rate = self.kokoro.create(
                    text, voice="af_sarah", speed=1.0, lang="en"
                )
                sf.write(filepath, samples, sample_rate)
            else:
                # Mock generation to prevent failing if ONNX models aren't present yet
                logger.info(f"Mock TTS generating dummy audio for: '{text[:30]}...' -> {filepath}")
                sample_rate = 22050
                samples = np.zeros(sample_rate, dtype=np.float32) # 1 second of silence
                sf.write(filepath, samples, sample_rate)
                
            return filepath
            
        except Exception as e:
            logger.error(f"TTS generation failed: {e}", exc_info=True)
            return None
