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
        logger.info(f"STT: Uploading and transcribing {audio_filepath}")
        
        if not os.path.exists(audio_filepath):
            logger.error(f"STT: Audio file not found: {audio_filepath}")
            return ""

        try:
            # Upload file to Gemini
            sample_file = genai.upload_file(path=audio_filepath)
            
            # Wait for processing if necessary (usually instant for small files)
            while sample_file.state.name == "PROCESSING":
                time.sleep(1)
                sample_file = genai.get_file(sample_file.name)

            if sample_file.state.name == "FAILED":
                raise Exception("Gemini audio processing failed")

            # Use Gemini to transcribe
            model = genai.GenerativeModel("models/gemini-1.5-flash")
            response = model.generate_content([
                "Transcribe the following audio precisely. If it is in Hindi, output in Devanagari script. Output ONLY the transcription, no extra text.",
                sample_file
            ])
            
            transcription = response.text.strip()
            logger.info(f"STT Result: '{transcription}'")
            
            # Cleanup: Delete the file from Gemini cloud
            genai.delete_file(sample_file.name)
            
            return transcription

        except Exception as e:
            logger.error(f"STT Error using Gemini: {e}")
            return "माफ़ कीजिये, क्या आप दोबारा कह सकते हैं?" # Fallback: "Sorry, can you say that again?"
