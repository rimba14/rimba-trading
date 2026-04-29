import os
import json
import logging
import time
from typing import Dict, Any, Optional
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from dotenv import load_dotenv

# Load configuration
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    # Fallback to GEMINI_API_KEY if exists
    GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")

class GeminiReasoningEngine:
    def __init__(self, model_name: str = "models/gemini-2.5-flash"):
        if not GOOGLE_API_KEY:
            logging.error("[GEMINI] No API key found in environment.")
            raise ValueError("GOOGLE_API_KEY missing.")
        
        genai.configure(api_key=GOOGLE_API_KEY)
        self.model = genai.GenerativeModel(model_name)
        self.logger = logging.getLogger("GeminiEngine")

    @retry(
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        retry=retry_if_exception_type(Exception)
    )
    def _generate_with_retry(self, prompt: str, system_instruction: str) -> str:
        """Internal method with tenacity retry logic."""
        try:
            # We use the model with system instruction if supported, or prepended
            chat = self.model.start_chat()
            full_prompt = f"{system_instruction}\n\n{prompt}"
            
            # Using 10s timeout as per Phase 5 directive
            response = self.model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json"
                ),
                request_options={"timeout": 10}
            )
            return response.text
        except Exception as e:
            if "429" in str(e) or "ResourceExhausted" in str(type(e)):
                self.logger.warning(f"Rate limited by Google AI Studio. Retrying with exponential backoff...")
            raise e

    async def json_with_retry_async(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Async interface for JSON reasoning."""
        # Simple wrap for now
        return self.json_with_retry(system_prompt, user_prompt)

    def json_with_retry(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """External interface for JSON reasoning."""
        start_time = time.time()
        try:
            raw_response = self._generate_with_retry(user_prompt, system_prompt)
            data = json.loads(raw_response)
            
            # Ensure required fields exist
            if "confidence" not in data: data["confidence"] = 0.5
            if "reasoning" not in data: data["reasoning"] = "No reasoning provided by model."
            
            elapsed = time.time() - start_time
            self.logger.info(f"[GEMINI] Inference complete in {elapsed:.2f}s")
            return data
            
        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(f"[GEMINI] Failed after {elapsed:.2f}s: {e}")
            return {
                "decision": "HOLD",
                "confidence": 0.5,
                "reasoning": f"Inference Error: {str(e)}"
            }

if __name__ == "__main__":
    # Test block
    logging.basicConfig(level=logging.INFO)
    engine = GeminiReasoningEngine()
    test_res = engine.json_with_retry(
        "You are a trading assistant. Return JSON with 'decision', 'confidence' (0-1), and 'reasoning'.",
        "Market is bullish on BTC. What is your conviction?"
    )
    print(json.dumps(test_res, indent=2))
