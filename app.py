import os
import logging
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from config import Config

# Fix import order issues: import queue_manager before usage
from queue_manager import queue_manager
from socket_manager import socketio

logger = logging.getLogger(__name__)

# Initialize Flask App
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

# Attach SocketIO
socketio.init_app(app)

# Start background worker immediately on load (handles single-process or master)
queue_manager.start()

@app.before_request
def ensure_worker_running():
    """
    Ensures the queue worker is running in Gunicorn worker processes.
    Threads do not survive forks, so this restarts it if it's dead.
    """
    queue_manager.start()

@app.route("/health", methods=["GET"])
def health_check():
    """Returns server status."""
    return jsonify({
        "status": "healthy",
        "queue_size": queue_manager.task_queue.qsize()
    }), 200

@app.route("/call", methods=["POST"])
def initiate_call():
    """
    Accepts customer data from Google Sheets (Trigger Layer)
    Validates input and adds request to the queue.
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Invalid JSON input"}), 400
        
    name = data.get("name")
    phone = data.get("phone")
    message = data.get("message", "")
    
    # Validation logic
    if not name or not phone:
        return jsonify({"error": "Fields 'name' and 'phone' are required."}), 400
        
    if not isinstance(phone, str) or len(phone.strip()) < 7:
        return jsonify({"error": "Invalid 'phone' format."}), 400
        
    task_data = {
        "name": name.strip(),
        "phone": phone.strip(),
        "message": message.strip() if message else ""
    }
    
    # Add to queue (DO NOT process immediately)
    queue_manager.add_task(task_data)
    
    return jsonify({
        "status": "queued",
        "message": f"Call to {task_data['phone']} has been added to the queue."
    }), 202

@app.route("/dispatch-call", methods=["POST"])
def dispatch_call():
    """
    HTTP Fallback Webhook for dispatching a call.
    Used if no WebSockets are connected.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
        
    phone = data.get("phone")
    audio_url = data.get("audio_url")
    call_id = data.get("call_id")
    
    logger.info(f"[HTTP FALLBACK] Received dispatch for {phone} (Call ID: {call_id}) | Audio: {audio_url}")
    return jsonify({"status": "dispatched_via_http"}), 200

@app.route("/receive-audio", methods=["POST"])
def receive_audio():
    """
    HTTP Fallback for receiving audio.
    Input: audio file (customer speech), call_id
    Process: STT -> Gemini -> TTS -> Returns new audio URL.
    """
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
        
    call_id = request.form.get("call_id")
    if not call_id:
        return jsonify({"error": "call_id required"}), 400
        
    audio_file = request.files['audio']
    filename = secure_filename(audio_file.filename or f"{call_id}.wav")
    
    upload_dir = os.path.join(os.path.dirname(__file__), 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    
    filepath = os.path.join(upload_dir, filename)
    audio_file.save(filepath)
    
    try:
        audio_url = queue_manager.call_handler.process_audio_response(call_id, filepath)
        return jsonify({"audio_url": audio_url}), 200
        
    except Exception as e:
        logger.error(f"Error in HTTP /receive-audio: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/audio/<filename>", methods=["GET"])
def get_audio(filename):
    """
    Provides public URLs for the generated audio files.
    """
    audio_dir = os.path.join(os.path.dirname(__file__), 'audio_files')
    return send_from_directory(audio_dir, filename)

if __name__ == "__main__":
    logger.info(f"Starting Flask-SocketIO App on port {Config.PORT}")
    # Using SocketIO run method. allow_unsafe_werkzeug ensures it runs on newer Werkzeug versions locally
    socketio.run(app, host="0.0.0.0", port=Config.PORT, allow_unsafe_werkzeug=True)
