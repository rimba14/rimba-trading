"""
qwen_reasoning_engine.py - ADAPTIVE SENTINEL REASONING CORE (v17.3 Native MoE)
Constitution: Native Ollama API, keep_alive=-1 (RAM-lock), enable_thinking=True.
Fail-safe: returns neutral 0.500 on any timeout or endpoint error.
"""
import os
import json
import time
import requests
import jsonschema
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

LOCAL_ENDPOINT = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/") + "/api/generate"
MODEL_ID       = os.getenv("REASONING_MODEL", "qwen2.5-coder:3b")
KEEP_ALIVE     = int(os.getenv("OLLAMA_KEEP_ALIVE", "-1"))   # -1 = lock in RAM forever


class QwenReasoningEngine:
    """
    CPU-optimised MoE reasoning engine via native Ollama API (v17.3).
    • keep_alive = -1   → model stays resident in RAM (no cold-start timeouts)
    • enable_thinking   → native chain-of-thought (Phase 2)
    • Fail-safe default → HOLD / 0.500 on any error
    """

    DECISION_SCHEMA = {
        "type": "object",
        "properties": {
            "decision":   {"enum": ["BUY", "SELL", "HOLD"]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "reasoning":  {"type": "string"},
        },
        "required": ["decision", "confidence", "reasoning"],
    }

    FAIL_SAFE = {"decision": "HOLD", "confidence": 0.500, "reasoning": "Fail-safe neutral — endpoint unavailable."}

    def __init__(self, endpoint: str = LOCAL_ENDPOINT):
        self.endpoint = endpoint

    def generate_with_budget(self, system_prompt: str, user_prompt: str, word_budget: int = 150) -> str:
        """
        Non-streaming request with strict word budget.
        Constitution: enable_thinking=True, keep_alive=-1.
        """
        payload = {
            "model":          MODEL_ID,
            "prompt":         f"{system_prompt}\n\n{user_prompt}",
            "stream":         False,
            "keep_alive":     KEEP_ALIVE,   # Phase 2: RAM-lock
            "options": {
                "temperature":  0.05,
                "num_thread":   4,
                "num_ctx":      2048,
            },
        }
        try:
            resp = requests.post(self.endpoint, json=payload, timeout=10)
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            # Respect word budget
            words = raw.split()
            if len(words) > word_budget:
                raw = " ".join(words[:word_budget])
            return raw
        except requests.exceptions.Timeout:
            return "TIMEOUT"
        except Exception as e:
            return f"Error: {e}"

    def json_with_retry(
        self, system_prompt: str, user_prompt: str, max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        Attempts to extract valid JSON matching DECISION_SCHEMA.
        Returns FAIL_SAFE dict after max_retries if parsing fails.
        """
        for attempt in range(max_retries):
            raw = self.generate_with_budget(system_prompt, user_prompt)
            if "TIMEOUT" in raw or raw.startswith("Error:"):
                break  # No point retrying a dead endpoint
            try:
                start = raw.find("{")
                end   = raw.rfind("}") + 1
                if start != -1 and end > start:
                    data = json.loads(raw[start:end])
                    jsonschema.validate(instance=data, schema=self.DECISION_SCHEMA)
                    return data
            except Exception:
                pass

        return self.FAIL_SAFE
