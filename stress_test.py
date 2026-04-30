import logging
import time
from tts_service import TTSService
import gc

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("StressTest")

def run_stress_test():
    logger.info("Initializing TTS Service...")
    service = TTSService()
    
    test_phrases = [
        "नमस्ते। आपका ऑर्डर कन्फर्म हो गया है।",
        "कृपया होल्ड करें, मैं आपकी जानकारी चेक कर रही हूँ।",
        "माफ़ कीजिये, मैं समझ नहीं पायी।",
        "क्या आप मुझे अपना फोन नंबर बता सकते हैं?",
        "धन्यवाद! आपका दिन शुभ हो।",
        "मैं आपकी कैसे मदद कर सकती हूँ?",
        "हम जल्द ही आपसे संपर्क करेंगे।",
        "क्या आपको किसी और जानकारी की आवश्यकता है?",
        "हमारी सर्विस बिल्कुल मुफ्त है।",
        "सिस्टम में कुछ तकनीकी समस्या है।"
    ]
    
    success_count = 0
    failure_count = 0
    
    start_time = time.time()
    
    for i in range(1, 51):
        phrase = test_phrases[i % len(test_phrases)] + f" (टेस्ट {i})"
        logger.info(f"--- Stress Test Request {i}/50 ---")
        
        req_start = time.time()
        result = service.text_to_speech(phrase)
        req_end = time.time()
        
        if result:
            success_count += 1
            logger.info(f"Request {i} successful in {req_end - req_start:.2f}s. Audio: {result}")
        else:
            failure_count += 1
            logger.error(f"Request {i} failed!")
            
        # Optional: Give a tiny delay to mimic realistic load
        time.sleep(0.1)
        
    total_time = time.time() - start_time
    logger.info("=========================================")
    logger.info("STRESS TEST COMPLETED")
    logger.info(f"Total Requests: 50")
    logger.info(f"Success: {success_count}")
    logger.info(f"Failed: {failure_count}")
    logger.info(f"Total Time: {total_time:.2f}s")
    logger.info(f"Average Time per Request: {total_time/50:.2f}s")
    
    # Final GC check
    gc.collect()
    service._log_memory("End of Stress Test")
    logger.info("=========================================")

if __name__ == "__main__":
    run_stress_test()
