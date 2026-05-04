"""
cascading_engine.py - ADAPTIVE SENTINEL CASCADING ENGINE (v18.0 — Groq-Centric Build)
Constitution: Groq (Primary) -> Gemini (Failover) with Jittered Exponential Backoff.
"""

import os
import json
import logging
import time
from typing import Dict, Any

from groq import Groq
import google.generativeai as genai
from google.generativeai import caching
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# ── Configuration ────────────────────────────────────────────────────────────
GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"

# Initialize Engines
_groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

logger = logging.getLogger("CascadingEngine")

class CascadingReasoningEngine:
    """
    Implements Phase 2: Cascading API Failover.
    Routes primarily to Groq. If 429/503, fails over to Gemini.
    """

    def __init__(self):
        self.logger = logger

    @retry(
        wait=wait_random_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception)
    )
    def _call_groq(self, system_prompt: str, user_prompt: str) -> str:
        if not _groq_client:
            raise ValueError("Groq client not initialized")
        
        # v18.0 Directive: Static data (Constitution) at top, Dynamic at bottom.
        # We assume system_prompt is static and user_prompt is dynamic.
        # Directive v18.0: Force JSON instruction to satisfy Groq JSON mode requirements.
        if "json" not in user_prompt.lower() and "json" not in system_prompt.lower():
            user_prompt += "\n\nCRITICAL: Return output EXCLUSIVELY as a JSON object."

        messages = [
            {"role": "system", "content": system_prompt if system_prompt else "You are a specialized trading agent."},
            {"role": "user", "content": user_prompt}
        ]
        
        response = _groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=1024
        )
        return response.choices[0].message.content

    @retry(
        wait=wait_random_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception)
    )
    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        # Use the GenerativeModel with the system instruction
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=system_prompt
        )
        
        response = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        return response.text

    def json_with_retry(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        Public entry point for cascading inference.
        """
        start_time = time.time()
        
        # 1. Primary: Groq
        try:
            self.logger.info(f"[CASCADING] Attempting Groq ({GROQ_MODEL})...")
            raw = self._call_groq(system_prompt, user_prompt)
            data = json.loads(raw)
            self.logger.info(f"[GROQ_SUCCESS] Inference complete in {time.time()-start_time:.2f}s")
            return data
        except Exception as e:
            self.logger.warning(f"[GROQ_FAIL] {e}. Failing over to Gemini...")
            
            # 2. Failover: Gemini
            try:
                self.logger.info(f"[CASCADING] Attempting Gemini ({GEMINI_MODEL})...")
                raw = self._call_gemini(system_prompt, user_prompt)
                data = json.loads(raw)
                self.logger.info(f"[GEMINI_SUCCESS] Failover complete in {time.time()-start_time:.2f}s")
                return data
            except Exception as e2:
                self.logger.error(f"[TOTAL_EXHAUSTION] Both Groq and Gemini failed: {e2}")
                # 3. Final Fail-Safe: Neutral 0.500
                return {
                    "decision": "HOLD",
                    "confidence": 0.500,
                    "reasoning": f"Total API Exhaustion. Groq Error: {e} | Gemini Error: {e2}"
                }

    async def json_with_retry_async(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        # Simple wrapper for now as the libraries are mostly synchronous or have their own async handlers
        return self.json_with_retry(system_prompt, user_prompt)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = CascadingReasoningEngine()
    test_sys = "You are a trader. Return JSON: {'decision': 'HOLD', 'confidence': 0.5}"
    test_user = "Price is 1.17. What do?"
    print(engine.json_with_retry(test_sys, test_user))
