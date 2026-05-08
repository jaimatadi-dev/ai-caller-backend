import logging
import os
import time
from google import generativeai as genai
from config import Config

logger = logging.getLogger(__name__)

class STTService:
    def __init__(self):
        # Configure Gemini using the first available key
        self.api_key = Config.GEMINI_API_KEY_1
        if self.api_key:
            genai.configure(api_key=self.api_key)
            logger.info("STT Service initialized with Gemini API")
        else:
            logger.warning("No Gemini API key for STT Service")

    def speech_to_text(self, audio_filepath: str) -> str:
        """
        Transcribes audio using Gemini AI.
        Supports Hindi and high-quality transcription.
        """
        logger.info(f"STT: Received processing request for {audio_filepath}")
        
        if not os.path.exists(audio_filepath):
            logger.error(f"STT: Audio file not found: {audio_filepath}")
            return ""

        # Noise check: if file is too small (e.g., < 2KB), it's likely just a click or silence
        file_size = os.path.getsize(audio_filepath)
        if file_size < 2048:
            logger.info(f"STT: File too small ({file_size} bytes), skipping processing as noise.")
            return ""

        try:
            logger.info(f"STT: Uploading {file_size} bytes to Gemini...")
            # Upload file to Gemini
            sample_file = genai.upload_file(path=audio_filepath)
            
            logger.info(f"STT: File uploaded as {sample_file.name}. Waiting for processing...")
            # Wait for processing if necessary (usually instant for small files)
            while sample_file.state.name == "PROCESSING":
                time.sleep(0.5)
                sample_file = genai.get_file(sample_file.name)

            if sample_file.state.name == "FAILED":
                raise Exception("Gemini audio processing failed")

            logger.info(f"STT: Transcription started...")
            # Use Gemini to transcribe
            model = genai.GenerativeModel("models/gemini-1.5-flash")
            response = model.generate_content([
                "The following is a phone call audio. Transcribe it precisely. If it is in Hindi, output in Devanagari script. If it is just noise or silence, output 'NOISE'. Output ONLY the transcription, no extra text.",
                sample_file
            ])
            
            transcription = response.text.strip()
            if transcription.upper() == "NOISE":
                logger.info("STT: Gemini identified audio as NOISE.")
                return ""
                
            logger.info(f"STT Result: '{transcription}'")
            
            # Cleanup: Delete the file from Gemini cloud
            genai.delete_file(sample_file.name)
            
            return transcription

        except Exception as e:
            logger.error(f"STT Error using Gemini: {e}")
            return ""
