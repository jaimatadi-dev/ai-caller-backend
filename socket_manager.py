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
    Expected data: { "call_id": "...", "audio_data": "base64_encoded_string" }
    """
    call_id = data.get("call_id")
    audio_b64 = data.get("audio_data") 
    
    if not call_id or not audio_b64:
        logger.warning("Received invalid audio_response WebSocket event (missing call_id or audio_data).")
        return {"status": "error", "message": "call_id and audio_data required"}
        
    logger.info(f"WebSocket audio received for call {call_id}")
    
    # Update call activity to prevent timeout
    from call_handler import call_state_manager
    call_state_manager.update_activity(call_id)
    
    upload_dir = os.path.join(os.path.dirname(__file__), 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    filename = secure_filename(f"{call_id}_ws.wav")
    filepath = os.path.join(upload_dir, filename)
    
    try:
        # Decode base64 and save as a wav file
        audio_bytes = base64.b64decode(audio_b64)
        with open(filepath, "wb") as f:
            f.write(audio_bytes)
            
        from queue_manager import queue_manager
        
        # Process the audio synchronously (STT -> Gemini -> TTS)
        audio_url = queue_manager.call_handler.process_audio_response(call_id, filepath)
        
        # Emit back the newly generated audio URL so Android bridge plays it
        socketio.emit("play_audio", {"audio_url": audio_url}, to=request.sid)
        logger.info(f"Emitted 'play_audio' for call {call_id} to SID {request.sid}")
        
    except Exception as e:
        logger.error(f"Error processing WS audio for {call_id}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@socketio.on("call_status")
def handle_call_status(data):
    """
    Handles generic call events from Android device.
    Expected data: { "call_id": "...", "status": "started|answered|ended" }
    """
    call_id = data.get("call_id")
    status = data.get("status") 
    
    if call_id and status:
        logger.info(f"WebSocket status update for call {call_id}: {status}")
        from call_handler import call_state_manager
        
        state = call_state_manager.get_call(call_id)
        if state:
            call_state_manager.update_status(call_id, status)
            call_state_manager.update_activity(call_id)

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
        logger.warning("No active WebSocket devices connected to emit 'new_call'")
