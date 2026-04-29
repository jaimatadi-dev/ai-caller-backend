import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CallAgent")

class Config:
    GEMINI_API_KEYS = [
        os.getenv("GEMINI_API_KEY_1"),
        os.getenv("GEMINI_API_KEY_2"),
        os.getenv("GEMINI_API_KEY_3"),
    ]
    # Filter out empty keys
    GEMINI_API_KEYS = [k for k in GEMINI_API_KEYS if k]
    
    PORT = int(os.getenv("PORT", 10000))
    MAX_RETRIES = 2
    RATE_LIMIT_DELAY = 5  # Max 10-12 req/min -> 60/12 = 5 seconds delay between calls
