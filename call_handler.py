import logging
import time
import uuid
import threading
import requests
from typing import Dict, Any, Optional
from gemini_service import GeminiService
from tts_service import TTSService
from stt_service import STTService
from config import Config

logger = logging.getLogger(__name__)

class CallState:
    def __init__(self):
        self.calls = {}
        self.lock = threading.Lock()

    def create_call(self, phone: str, name: str) -> str:
        call_id = str(uuid.uuid4())
        with self.lock:
            self.calls[call_id] = {
                "call_id": call_id,
                "phone": phone,
                "name": name,
                "history": [],
                "last_response": None,
                "last_activity_time": time.time(),
                "status": "active",
                "call_stage": "initialized"
            }
        return call_id

    def get_call(self, call_id: str) -> Optional[Dict]:
        with self.lock:
            return self.calls.get(call_id)

    def update_activity(self, call_id: str):
        with self.lock:
            if call_id in self.calls:
                self.calls[call_id]["last_activity_time"] = time.time()

    def update_status(self, call_id: str, status: str):
        with self.lock:
            if call_id in self.calls:
                self.calls[call_id]["call_stage"] = status
                if status == "ended":
                    self.calls[call_id]["status"] = "ended"
                    logger.info(f"Call {call_id} marked as ended from status update.")

    def end_call(self, call_id: str):
        with self.lock:
            if call_id in self.calls:
                self.calls[call_id]["status"] = "ended"
                self.calls[call_id]["call_stage"] = "ended"
                logger.info(f"Call ended for {call_id}.")

call_state_manager = CallState()

class CallHandler:
    def __init__(self):
        self.gemini_service = GeminiService()
        self.tts_service = TTSService()
        self.stt_service = STTService()

    def process_initial_call(self, task: Dict[str, Any]) -> bool:
        """
        Executes the initial outbound leg of the call.
        """
        name = task.get("name")
        phone = task.get("phone")
        message = task.get("message")
        
        try:
            print(f"[DEBUG] Creating call state for {phone}...", flush=True)
            call_id = call_state_manager.create_call(phone, name)
            logger.info(f"Call started for {name} ({phone}) | Call ID: {call_id}")
            print(f"[DEBUG] Call ID created: {call_id}", flush=True)
            
            # 1. Generate greeting
            print(f"[DEBUG] Calling Gemini for greeting ({phone})...", flush=True)
            text_response = self.gemini_service.generate_response(name, message, history=[])
            print(f"[DEBUG] Gemini responded: {text_response[:30]}...", flush=True)
            
            # Update state
            state = call_state_manager.get_call(call_id)
            state["history"].append({"role": "system", "content": text_response})
            state["last_response"] = text_response
            
            # 2. Convert to speech
            print(f"[DEBUG] Calling TTS Service...", flush=True)
            wav_filepath = self.tts_service.text_to_speech(text_response)
            if not wav_filepath:
                raise Exception("TTS Generation returned None.")
            print(f"[DEBUG] TTS complete, saved at {wav_filepath}", flush=True)
                
            audio_url = self._build_audio_url(wav_filepath)
            
            # 3. Send audio + phone to Mobile Bridge (WebSocket or HTTP fallback)
            print(f"[DEBUG] Dispatching to mobile bridge...", flush=True)
            self._dispatch_to_mobile(phone, audio_url, call_id)
            print(f"[DEBUG] Dispatched successfully.", flush=True)
            
            # 4. Start the timeout monitor loop
            print(f"[DEBUG] Starting timeout monitor thread...", flush=True)
            threading.Thread(target=self._monitor_call_timeout, args=(call_id,), daemon=True).start()
            
            print(f"[DEBUG] process_initial_call completed successfully.", flush=True)
            return True
            
        except Exception as e:
            print(f"[DEBUG] Exception in process_initial_call: {str(e)}", flush=True)
            logger.error(f"Initial call processing failed for {phone}: {e}", exc_info=True)
            return False

    def process_audio_response(self, call_id: str, audio_filepath: str) -> str:
        """
        Called when mobile bridge sends customer audio.
        Executes the real-time conversation loop.
        """
        state = call_state_manager.get_call(call_id)
        if not state or state["status"] != "active":
            raise Exception("Call is not active or invalid Call ID.")
            
        call_state_manager.update_activity(call_id)
        logger.info(f"Audio pipeline triggered for call {call_id}")
        
        # 1. Convert speech to text
        user_text = self.stt_service.speech_to_text(audio_filepath)
        state["history"].append({"role": "user", "content": user_text})
        
        # 2 & 3. Send text to Gemini and generate response
        ai_text = self.gemini_service.generate_response(state["name"], user_text, state["history"])
        state["history"].append({"role": "system", "content": ai_text})
        state["last_response"] = ai_text
        logger.info(f"AI response for {call_id}: {ai_text}")
        
        # 4. Convert to speech
        wav_filepath = self.tts_service.text_to_speech(ai_text)
        audio_url = self._build_audio_url(wav_filepath)
        
        logger.info(f"Generated next audio URL for call {call_id}: {audio_url}")
        return audio_url

    def _dispatch_to_mobile(self, phone: str, audio_url: str, call_id: str):
        """
        Sends the initial call instruction to the Mobile Bridge endpoint via WebSocket or HTTP fallback.
        """
        logger.info(f"--- DISPATCHING CALL TO MOBILE BRIDGE ---")
        logger.info(f"Call ID: {call_id}")
        logger.info(f"Dialing Phone: {phone}")
        logger.info(f"Audio URL: {audio_url}")
        logger.info(f"-----------------------------------------")
        
        try:
            # Import dynamically to avoid circular dependencies
            from socket_manager import emit_new_call, active_devices
            
            if active_devices:
                emit_new_call(call_id, phone, audio_url)
            else:
                logger.info("No WebSocket devices connected. Falling back to HTTP /dispatch-call webhook.")
                requests.post(
                    f"http://127.0.0.1:{Config.PORT}/dispatch-call",
                    json={"phone": phone, "audio_url": audio_url, "call_id": call_id},
                    timeout=5
                )
        except Exception as e:
            logger.warning(f"Failed to dispatch call: {e}")

    def _build_audio_url(self, filepath: str) -> str:
        filename = filepath.replace('\\', '/').split('/')[-1]
        return f"http://127.0.0.1:{Config.PORT}/audio/{filename}"

    def _monitor_call_timeout(self, call_id: str):
        """
        Timeout Handling Loop: If no response from phone in 30 seconds -> end call.
        """
        while True:
            time.sleep(5)
            state = call_state_manager.get_call(call_id)
            
            if not state or state["status"] != "active":
                break
                
            if time.time() - state["last_activity_time"] > 30:
                logger.info(f"Call {call_id} ended due to 30-second timeout.")
                call_state_manager.end_call(call_id)
                break
