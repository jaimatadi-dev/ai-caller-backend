import logging
import time
from typing import Optional
from google import generativeai as genai
from config import Config

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self):
        self.api_keys = [
            Config.GEMINI_API_KEY_1,
            Config.GEMINI_API_KEY_2,
            Config.GEMINI_API_KEY_3
        ]
        self.api_keys = [k for k in self.api_keys if k]
        self.current_key_index = 0
        self.requests_this_minute = 0
        self.minute_start_time = time.time()
        
        if self.api_keys:
            genai.configure(api_key=self.api_keys[self.current_key_index])
            logger.info("Gemini Service initialized with API key 1")
        else:
            logger.warning("No Gemini API keys provided in environment.")

    def _rotate_key(self) -> bool:
        if not self.api_keys:
            return False
            
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        
        if self.current_key_index == 0:
            return False 
            
        new_key = self.api_keys[self.current_key_index]
        genai.configure(api_key=new_key)
        logger.info(f"Rotated to fallback Gemini API key {self.current_key_index + 1}")
        return True

    def _check_rate_limit(self):
        current_time = time.time()
        if current_time - self.minute_start_time > 60:
            self.requests_this_minute = 0
            self.minute_start_time = current_time
            
        if self.requests_this_minute >= Config.GEMINI_RATE_LIMIT_PER_MIN:
            sleep_time = 60 - (current_time - self.minute_start_time)
            if sleep_time > 0:
                logger.warning(f"Global rate limit reached. Sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)
            
            self.requests_this_minute = 0
            self.minute_start_time = time.time()

    def generate_response(self, name: str, user_message: Optional[str] = None, history: list = None) -> str:
        """
        Generates a response using predefined rules (optimization) or Gemini AI.
        Injects conversation history for context.
        """
        user_message_clean = user_message.lower().strip() if user_message else ""
        
        # PREDEFINED RESPONSE OPTIMIZATIONS (Only apply if no history)
        if not history and (not user_message_clean or user_message_clean in ["hello", "hi", "hey"]):
            logger.info("Using predefined greeting, saving Gemini API call.")
            return f"Namaste {name}, main aapki call agent hoon. Main aapki kis tarah se sahayata kar sakti hoon?"

        if "price" in user_message_clean or "cost" in user_message_clean or "charge" in user_message_clean:
            logger.info("Using predefined pricing response, saving Gemini API call.")
            return "Hamari service bilkul zero cost aur free of charge hai. Kya aapko aur koi jankari chahiye?"
            
        if "bye" in user_message_clean or "thank" in user_message_clean:
            logger.info("Using predefined closing response.")
            return "Call karne ke liye dhanyawad. Aapka din shubh ho."

        # USE GEMINI AI for custom questions
        if not self.api_keys:
            logger.error("Cannot use Gemini AI: No API keys configured.")
            return "Maaf kijiye, abhi system me technical issue hai. Hum aapse baad me sampark karenge."

        history_context = ""
        if history:
            for msg in history[-5:]: # Keep last 5 turns to save context length
                role = "Customer" if msg["role"] == "user" else "Agent"
                history_context += f"{role}: {msg['content']}\n"

        prompt = (
            f"You are a polite Indian call agent speaking in Hinglish.\n"
            f"Customer name: {name}\n"
            f"Goal: Greet the user, ask their requirement, and guide them about the service.\n"
            f"Keep responses short, natural, and conversational.\n\n"
            f"Conversation History:\n{history_context}\n"
            f"Customer says: {user_message}"
        )

        # SAFE FALLBACK LOGIC
        for attempt in range(len(self.api_keys) + 1):
            self._check_rate_limit()
            try:
                self.requests_this_minute += 1
                logger.info(f"Calling Gemini AI (Using Key {self.current_key_index + 1})")
                
                model = genai.GenerativeModel("models/gemini-2.5-flash")
                response = model.generate_content(prompt)
                
                if hasattr(response, "text") and response.text:
                    return response.text.strip()
                
                try:
                    return response.candidates[0].content.parts[0].text.strip()
                except:
                    return "Maaf kijiye, mujhe samajh nahi aaya. Kya aap dohra sakte hain?"
                
            except Exception as e:
                error_msg = str(e).lower()
                logger.error(f"Gemini API failure on key {self.current_key_index + 1}: {e}")
                
                if "429" in error_msg or "timeout" in error_msg or "rate limit" in error_msg or "quota" in error_msg:
                    if self._rotate_key():
                        continue
                    else:
                        logger.error("All fallback API keys exhausted or rate limited.")
                        break
                else:
                    if attempt == 0 and self._rotate_key():
                        continue
                    break

        return "Maaf kijiye, mujhe samajh nahi aaya. Kya aap dohra sakte hain?"
