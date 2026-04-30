import os
import logging
import uuid
import hashlib
import random
import re
import gc
import psutil
from typing import Optional
import soundfile as sf
import numpy as np

logger = logging.getLogger(__name__)

class TTSService:
    _instance = None
    
    def __new__(cls):
        # Singleton pattern
        if cls._instance is None:
            cls._instance = super(TTSService, cls).__new__(cls)
            cls._instance._init_service()
        return cls._instance

    def _init_service(self):
        # 4. Smart Caching: ./audio_cache/
        base_dir = os.path.dirname(__file__)
        self.cache_dir = os.path.join(base_dir, 'audio_cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self.tts = None
        self._load_model()
        
    def _log_memory(self, stage: str):
        try:
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / (1024 * 1024)
            logger.info(f"Memory Usage [{stage}]: {mem_mb:.2f} MB")
        except Exception:
            pass
            
    def _load_model(self):
        try:
            import sherpa_onnx
        except ImportError:
            logger.error("sherpa-onnx package not installed.")
            return

        self._log_memory("Before Model Load")
        
        # 1. Model Loading (NO auto-download)
        # Load model ONLY from local directory ./models/hi_IN/
        base_dir = os.path.dirname(__file__)
        model_dir = os.path.join(base_dir, "models", "hi_IN")
        
        if not os.path.exists(model_dir):
            logger.error(f"Model directory not found: {model_dir}. Please ensure model files are placed here.")
            return
            
        onnx_file = ""
        tokens_file = ""
        data_dir = ""
        for root, dirs, files in os.walk(model_dir):
            if "espeak-ng-data" in dirs:
                data_dir = os.path.join(root, "espeak-ng-data")
            for f in files:
                if f.endswith(".onnx"):
                    onnx_file = os.path.join(root, f)
                elif f == "tokens.txt":
                    tokens_file = os.path.join(root, f)
                    
        if not onnx_file or not tokens_file or not data_dir:
            logger.error("Could not find required Sherpa-ONNX files (ONNX, tokens, or espeak-ng-data) in ./models/hi_IN/")
            return
            
        try:
            vits = sherpa_onnx.OfflineTtsVitsModelConfig(
                model=onnx_file,
                tokens=tokens_file,
                data_dir=data_dir,
            )
            
            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(vits=vits),
                max_num_sentences=1,
            )
            
            self.tts = sherpa_onnx.OfflineTts(tts_config)
            logger.info("Sherpa-ONNX Hindi TTS model loaded successfully (Singleton).")
            self._log_memory("After Model Load")
        except Exception as e:
            logger.error(f"Error loading Sherpa-ONNX model: {e}")

    def get_cache_key(self, text: str) -> str:
        safe_text = text.strip().lower()
        hash_id = hashlib.md5(safe_text.encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, f"cache_{hash_id}.wav")
        
    def _split_into_sentences(self, text: str) -> list:
        # 2. Text Processing (DO NOT truncate blindly)
        if not text:
            return []
            
        text = text.strip()
        # Ensure punctuation at the end
        if not text.endswith(('।', '.', '?', '!')):
            text += '।'
            
        # Split text into small natural sentences
        parts = re.split(r'([।?!.])', text)
        sentences = []
        for i in range(0, len(parts)-1, 2):
            sentence = parts[i].strip() + parts[i+1]
            if sentence.strip() and len(sentence.strip()) > 1:
                sentences.append(sentence.strip())
                
        if len(parts) % 2 != 0 and parts[-1].strip():
            sentences.append(parts[-1].strip() + '।')
            
        return sentences

    def text_to_speech(self, text: str) -> Optional[str]:
        if not text:
            return None
            
        try:
            # Check cache first
            cache_path = self.get_cache_key(text)
            if os.path.exists(cache_path):
                logger.info(f"Using cached audio for text: '{text[:30]}...'")
                return cache_path
            
            return self._generate_audio(text, cache_path)
            
        except Exception as e:
            logger.error(f"TTS generation error: {e}", exc_info=True)
            return self._get_fallback_audio()

    def _generate_audio(self, text: str, output_path: str) -> Optional[str]:
        if not self.tts:
            logger.error("TTS generation failed: Sherpa-ONNX model is not loaded.")
            return None

        self._log_memory("Before Generation")
        logger.info(f"Generating TTS for text: '{text[:30]}...'")
        
        # 3. Audio Generation Optimization (sentence-wise)
        sentences = self._split_into_sentences(text)
        all_samples = []
        sample_rate = None
        
        try:
            for i, sentence in enumerate(sentences):
                try:
                    audio = self.tts.generate(sentence)
                    if audio and len(audio.samples) > 0:
                        all_samples.append(audio.samples)
                        if sample_rate is None:
                            sample_rate = audio.sample_rate
                        
                        # Add slight natural silence (150ms) between chunks to avoid clipping
                        if i < len(sentences) - 1:
                            silence = np.zeros(int(sample_rate * 0.15), dtype=np.float32)
                            all_samples.append(silence)
                            
                except Exception as e:
                    logger.error(f"Failed to generate audio for sentence '{sentence}': {e}")
                    
            if not all_samples:
                return self._get_fallback_audio()
                
            # Write directly to destination (concatenating dynamically instead of multiple disk writes)
            final_audio = np.concatenate(all_samples)
            sf.write(output_path, final_audio, sample_rate)
            
            logger.info(f"Generated TTS file: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error compiling final audio chunks: {e}")
            return self._get_fallback_audio()
            
        finally:
            # 6. Memory Optimization: Let garbage collector clean up heavy audio arrays
            if 'final_audio' in locals():
                del final_audio
            if 'all_samples' in locals():
                del all_samples
            if 'audio' in locals():
                del audio
                
            gc.collect()
            self._log_memory("After Generation (GC Cleaned)")
        
    def _get_fallback_audio(self) -> str:
        # 5. Fallback System: Multiple variations randomly
        fallbacks = [
            "माफ़ कीजिये, मैं समझ नहीं पायी।",
            "कृपया दोबारा बताइए।",
            "थोड़ा साफ़ बोलिए।"
        ]
        text = random.choice(fallbacks)
        cache_path = self.get_cache_key(text)
        
        if os.path.exists(cache_path):
            return cache_path
            
        try:
            audio = self.tts.generate(text)
            sf.write(cache_path, audio.samples, audio.sample_rate)
            return cache_path
        except Exception as e:
            logger.error(f"Critical failure in fallback TTS: {e}")
            return ""
