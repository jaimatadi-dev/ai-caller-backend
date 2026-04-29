import queue
import threading
import logging
from typing import Dict, Any
from call_handler import CallHandler
from config import Config

logger = logging.getLogger(__name__)

class QueueManager:
    def __init__(self):
        # In-memory queue as abstraction. Can be easily swapped for Redis + RQ/Celery
        self.task_queue = queue.Queue()
        self.call_handler = CallHandler()
        self.is_running = False
        self.worker_thread = None


    def start(self):
        # In Gunicorn, if the process forks, the thread might be dead even if is_running is True.
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.is_running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            print("🚀 Queue worker started", flush=True)
            logger.info("🚀 Queue worker started")

    def add_task(self, task_data: Dict[str, Any]):
        """Adds a new call task to the queue."""
        task = {
            "name": task_data.get("name"),
            "phone": task_data.get("phone"),
            "message": task_data.get("message", ""),
            "status": "queued",
            "retry_count": 0
        }
        self.task_queue.put(task)
        logger.info(f"Task queued. Target: {task['phone']} | Queue size: {self.task_queue.qsize()}")

    def _worker_loop(self):
        """Runs continuously, picking and executing tasks sequentially."""
        while self.is_running:
            try:
                # Block until a task is available (1 sec timeout allows clean shutdown checking)
                task = self.task_queue.get(timeout=1)
                
                print(f"📞 Processing task: {task}", flush=True)
                logger.info(f"📞 Processing task: {task}")
                logger.info(f"Popped task for {task['phone']} (Attempt {task['retry_count'] + 1})")
                
                # Process Call
                success = self.call_handler.process_initial_call(task)
                
                if not success and task["retry_count"] < Config.MAX_RETRIES:
                    task["retry_count"] += 1
                    logger.warning(f"Task failed for {task['phone']}. Re-queuing for retry ({task['retry_count']}/{Config.MAX_RETRIES}).")
                    self.task_queue.put(task)
                elif not success:
                    logger.error(f"Task permanently failed for {task['phone']} after {Config.MAX_RETRIES} retries. Marking as failed.")
                else:
                    print(f"✅ Task processed successfully for {task['phone']}", flush=True)
                    logger.info(f"Task completed successfully for {task['phone']}.")
                
                self.task_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Unexpected error in queue worker loop: {e}", exc_info=True)

# Global singleton instance
queue_manager = QueueManager()
