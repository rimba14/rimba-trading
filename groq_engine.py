import os
import json
import logging
import time
from typing import Dict, Any, Optional
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from dotenv import load_dotenv

# Load configuration
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class GroqReasoningEngine:
    def __init__(self, model_name: str = "llama-3.1-8b-instant"): # Default to available fast model
        if not GROQ_API_KEY:
            logging.error("[GROQ] No API key found in environment.")
            raise ValueError("GROQ_API_KEY missing.")
        
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model_name = model_name
        self.logger = logging.getLogger("GroqEngine")

    @retry(
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        retry=retry_if_exception_type(Exception)
    )
    def _generate_with_retry(self, prompt: str, system_instruction: str) -> str:
        """Internal method with tenacity retry logic for Groq."""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                timeout=10
            )
            return response.choices[0].message.content
        except Exception as e:
            if "429" in str(e) or "Rate limit" in str(e):
                self.logger.warning(f"Rate limited by Groq API. Retrying with exponential backoff...")
            raise e

    async def json_with_retry_async(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Async interface for JSON reasoning (used in v17.7 Slow Loop)."""
        # Since groq-python doesn't have a native async client easily accessible in this env
        # we'll wrap the sync call. In a real v17.7, we'd use AsyncGroq.
        # But for this simulation, we'll keep it simple or use the sync call.
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
            self.logger.info(f"[GROQ] Inference complete in {elapsed:.2f}s")
            return data
            
        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(f"[GROQ] Failed after {elapsed:.2f}s: {e}")
            return {
                "decision": "HOLD",
                "confidence": 0.5,
                "reasoning": f"Inference Error: {str(e)}"
            }

if __name__ == "__main__":
    # Test block
    logging.basicConfig(level=logging.INFO)
    engine = GroqReasoningEngine()
    test_res = engine.json_with_retry(
        "You are a trading assistant. Return JSON with 'decision', 'confidence' (0-1), and 'reasoning'.",
        "Market is bullish on BTC. What is your conviction?"
    )
    print(json.dumps(test_res, indent=2))
