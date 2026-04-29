import os
import logging
import sys

class Config:
    GEMINI_API_KEY_1 = os.environ.get("GEMINI_API_KEY_1")
    GEMINI_API_KEY_2 = os.environ.get("GEMINI_API_KEY_2")
    GEMINI_API_KEY_3 = os.environ.get("GEMINI_API_KEY_3")
    PORT = int(os.environ.get("PORT", 10000))
    MAX_RETRIES = 2
    GEMINI_RATE_LIMIT_PER_MIN = 10

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    
    # Structured JSON-like logging format
    formatter = logging.Formatter(
        '{"time": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "message": "%(message)s"}'
    )
    handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(handler)

setup_logging()
