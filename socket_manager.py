import logging
import base64
import os
from werkzeug.utils import secure_filename
from flask import request
from flask_socketio import SocketIO

logger = logging.getLogger(__name__)

# Initialize SocketIO with threading mode since we rely on our thread-safe queue.
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')

# In-memory device registry { device_id: session_id }
active_devices = {}

@socketio.on("connect")
def handle_connect():
    logger.info(f"WebSocket client connected: {request.sid}")

@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    device_to_remove = None
    for device_id, s in active_devices.items():
        if s == sid:
            device_to_remove = device_id
            break
    if device_to_remove:
        del active_devices[device_to_remove]
        logger.info(f"WebSocket device disconnected: {device_to_remove}")
    else:
        logger.info(f"WebSocket client disconnected: {sid}")

@socketio.on("register_device")
def handle_register(data):
    """
    Registers an Android bridge device ID with its current WebSocket session.
    """
    device_id = data.get("device_id")
    if device_id:
        active_devices[device_id] = request.sid
        logger.info(f"Registered WebSocket device '{device_id}' with SID {request.sid}")
        return {"status": "registered"}
    return {"status": "error", "message": "device_id missing"}

@socketio.on("audio_response")
def handle_audio_response(data):
    """
    Receives customer audio from the Android bridge over WebSocket.
    Expected data: { "call_id": "...", "audio": "base64_encoded_string" }
    """
    call_id = data.get("call_id")
    audio_b64 = data.get("audio") 
    
    logger.info(f"📥 Received audio_response for call: {call_id} (size: {len(audio_b64) if audio_b64 else 0})")

    if not call_id or not audio_b64:
        logger.warning("Received invalid audio_response WebSocket event (missing call_id or audio).")
        return {"status": "error", "message": "call_id and audio required"}
        
    logger.info(f"[FLOW] Audio received from Android Bridge for call {call_id}")
    
    # Update call activity to prevent timeout
    from call_handler import call_state_manager
    call_state_manager.update_activity(call_id)
    
    upload_dir = os.path.join(os.path.dirname(__file__), 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    filename = secure_filename(f"{call_id}_ws.wav")
    filepath = os.path.join(upload_dir, filename)
    
    try:
        # 1. Convert base64 and save as a proper WAV file with header
        import wave
        audio_bytes = base64.b64decode(audio_b64)
        
        with wave.open(filepath, "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2) # 16-bit PCM (2 bytes)
            wav_file.setframerate(16000) # 16kHz
            wav_file.writeframes(audio_bytes)
            
        logger.info(f"Saved incoming PCM to WAV: {filepath}")
            
        from queue_manager import queue_manager
        
        # 2, 3, 4, 5. Process the audio synchronously (STT -> Gemini -> TTS)
        audio_url = queue_manager.call_handler.process_audio_response(call_id, filepath)
        
        # Memory Safety: Clean temporary user audio file
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # 6. Emit back the newly generated audio URL so Android bridge plays it
        socketio.emit("play_audio", {"audio_url": audio_url}, to=request.sid)
        logger.info(f"[FLOW] Audio sent back to Android Bridge for call {call_id}: {audio_url}")
        
    except Exception as e:
        logger.error(f"Error processing WS audio for {call_id}: {e}", exc_info=True)
        # Ensure cleanup even on error
        if os.path.exists(filepath):
            os.remove(filepath)
        return {"status": "error", "message": str(e)}

@socketio.on("call_started")
def handle_call_started(data):
    call_id = data.get("call_id")
    logger.info(f"Android Bridge Event: call_started for ID {call_id}")
    if call_id:
        from call_handler import call_state_manager
        call_state_manager.update_status(call_id, "started")
        call_state_manager.update_activity(call_id)

@socketio.on("call_answered")
def handle_call_answered(data):
    call_id = data.get("call_id")
    logger.info(f"Android Bridge Event: call_answered for ID {call_id}")
    if call_id:
        from call_handler import call_state_manager
        call_state_manager.update_status(call_id, "answered")
        call_state_manager.update_activity(call_id)

@socketio.on("call_ended")
def handle_call_ended(data):
    call_id = data.get("call_id")
    logger.info(f"Android Bridge Event: call_ended for ID {call_id}")
    if call_id:
        from call_handler import call_state_manager
        call_state_manager.end_call(call_id)

def emit_new_call(call_id: str, phone: str, audio_url: str):
    """
    Called by CallHandler to dispatch a new call to connected Android devices.
    """
    data = {
        "call_id": call_id,
        "phone": phone,
        "audio_url": audio_url
    }
    
    if active_devices:
        # Broadcast to all connected Android bridges (or target a specific one if needed)
        socketio.emit("new_call", data)
        logger.info(f"Broadcasted 'new_call' to {len(active_devices)} active WebSocket devices.")
    else:
        logger.warning("No active device available")
