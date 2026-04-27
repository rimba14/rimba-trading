"""
qwen_reasoning_engine.py - ADAPTIVE SENTINEL REASONING CORE
Integrated Thinking Budget and JSON Retry Logic for TurboQuant CPU Backend.
"""

import os
import json
import time
import openai
import jsonschema
from typing import Dict, Any, Optional

# --- Configuration (Directive 1: Maintain Endpoint) ---
LOCAL_ENDPOINT = "http://127.0.0.1:11434/v1"
API_KEY = "EMPTY"
MODEL_ID = "qwen2.5-coder:3b" # Mixture-of-Experts logic (v16.9)

class QwenReasoningEngine:
    """
    A CPU-optimized reasoning engine that manages a 'Thinking Budget' 
    via streaming and enforces strict JSON schema validation.
    """
    
    # Fast Loop Decision Schema (Directive 3)
    DECISION_SCHEMA = {
        "type": "object",
        "properties": {
            "decision": {"enum": ["BUY", "SELL", "HOLD"]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "reasoning": {"type": "string"}
        },
        "required": ["decision", "confidence", "reasoning"]
    }

    def __init__(self, base_url: str = LOCAL_ENDPOINT, api_key: str = API_KEY):
        self.client = openai.OpenAI(base_url=base_url, api_key=api_key)

    def generate_with_budget(self, system_prompt: str, user_prompt: str, budget: int = 250) -> str:
        """
        Directive 2: Implement Thinking Budget via streaming.
        Parses <think> tags and abruptly closes if over budget.
        """
        full_response = ""
        think_token_count = 0
        in_think_block = False
        budget_exceeded = False

        try:
            # Initialize streaming session (Directive: OOM Protocol)
            stream = self.client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                stream=True,
                extra_body={
                    "num_thread": 2,
                    "num_batch": 128,
                    "num_ctx": 4096,
                    "kv_cache_type": "q4_0"
                }
            )

            print(f"[REASONING] Initializing inference for {MODEL_ID}...")

            for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                full_response += content

                # Monitor for thinking start
                if "<think>" in full_response and not in_think_block:
                    in_think_block = True
                    print("[SENTINEL] Model entered reasoning phase.")

                if in_think_block:
                    # Estimate budget usage (words as proxy for tokens on CPU)
                    think_token_count += len(content.split())
                    
                    if think_token_count > budget:
                        print(f"⚠️ [BUDGET] Limit of {budget} reached. Forcing decision phase...")
                        stream.close() # Directive 2: Abruptly close connection
                        budget_exceeded = True
                        break

                # Monitor for thinking end
                if "</think>" in full_response and in_think_block:
                    in_think_block = False
                    print(f"[SENTINEL] Reasoning complete within {think_token_count} tokens.")

            if budget_exceeded:
                # Manually heal the thinking block and re-prompt for the final JSON
                healed_context = full_response + "\n</think>\n"
                return self._force_decision(system_prompt, user_prompt, healed_context)

            return full_response

        except Exception as e:
            print(f"[FATAL] Reasoning Stream Error: {e}")
            return ""

    def _force_decision(self, sys: str, user: str, context: str) -> str:
        """Healer function for budget-exhausted agents."""
        print("[SENTINEL] Re-prompting for final decision summary...")
        try:
            resp = self.client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": context},
                    {"role": "user", "content": "Summarize your final decision as JSON now."}
                ],
                temperature=0.1, # Low temp for structured output
                extra_body={
                    "num_thread": 2,
                    "num_batch": 128,
                    "num_ctx": 4096,
                    "kv_cache_type": "q4_0"
                }
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"[ERROR] Decision recovery failed: {e}")
            return context # Return what we have

    def json_with_retry(self, system_prompt: str, user_prompt: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Directive 3: Strict Schema Validation with Retry Logic.
        Uses jsonschema to ensure the Fast Loop receives valid data.
        """
        current_user_prompt = user_prompt
        
        for attempt in range(max_retries):
            raw_output = self.generate_with_budget(system_prompt, current_user_prompt)
            
            if not raw_output:
                print(f"[RETRY {attempt+1}] Empty response. Retrying...")
                continue

            try:
                # 1. Extraction (handle markdown code blocks and loose text)
                clean_json = raw_output.strip()
                
                # Try to find JSON block
                if "{" in clean_json and "}" in clean_json:
                    start_index = clean_json.find("{")
                    end_index = clean_json.rfind("}") + 1
                    clean_json = clean_json[start_index:end_index]
                
                # 2. Parsing
                data = json.loads(clean_json)
                
                # 3. Validation
                jsonschema.validate(instance=data, schema=self.DECISION_SCHEMA)
                
                print(f"[SUCCESS] Decision validated on attempt {attempt+1}.")
                return data

            except (json.JSONDecodeError, jsonschema.ValidationError) as e:
                print(f"[RETRY {attempt+1}] Validation failed: {e}")
                # Inject failure feedback for the next attempt
                current_user_prompt = (
                    f"{user_prompt}\n\n"
                    f"CRITICAL: Your previous response failed schema validation. "
                    f"You must return ONLY the raw JSON object, no extra text.\n"
                    f"Example format: {{\"decision\": \"BUY\", \"confidence\": 0.9, \"reasoning\": \"Strong breakout\"}}"
                )
                time.sleep(1) 

        # Failure Fallback
        return {
            "decision": "HOLD",
            "confidence": 0.0,
            "reasoning": "Max retries exceeded or validation failed."
        }

if __name__ == "__main__":
    # Internal Unit Test
    engine = QwenReasoningEngine()
    
    test_sys = "You are Moon Dev's Master Trading Agent. Analyze the signal and provide a JSON decision. Use <think> tags for your reasoning."
    test_user = "SYMBOL: BTCUSD | SIGNAL: RSI Oversold + MACD Bullish Cross. Elaborate deeply on why this is a good setup before deciding."
    
    print("--- STARTING REASONING TEST ---")
    final_decision = engine.json_with_retry(test_sys, test_user)
    print("\n" + "="*50)
    print("FINAL JSON OUTPUT:")
    print(json.dumps(final_decision, indent=4))
    print("="*50)
