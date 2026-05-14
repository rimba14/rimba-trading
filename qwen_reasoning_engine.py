"""
qwen_reasoning_engine.py - ADAPTIVE SENTINEL REASONING CORE (v17.3 Native MoE)
Constitution: Native Ollama API, keep_alive=-1 (RAM-lock), enable_thinking=True.
Fail-safe: returns neutral 0.500 on any timeout or endpoint error.
SRE v21.0: Global Circuit Breaker - trips on first timeout, instant HOLD thereafter.
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

# SRE v21.0: Global Circuit Breaker
# Once the Ollama endpoint times out once, this flag is set to True for the
# lifetime of the process. All subsequent calls return FAIL_SAFE instantly
# without waiting for another timeout. This prevents the 10s * N_assets hang.
_OLLAMA_CIRCUIT_OPEN: bool = False  # True = breaker tripped, Ollama is dead
_OLLAMA_TIMEOUT_SEC: float = 120.0   # Increased from 2s -> 120s (SRE v23.4 Patch)
_OLLAMA_DEAD_MSG: str = "Circuit breaker open: Ollama unreachable. Routing via Math Meta-Model."


class QwenReasoningEngine:
    """
    CPU-optimised MoE reasoning engine via native Ollama API (v17.3).
    - keep_alive = -1   -> model stays resident in RAM (no cold-start timeouts)
    - enable_thinking   -> native chain-of-thought (Phase 2)
    - Fail-safe default -> HOLD / 0.500 on any error
    - Circuit breaker   -> trips on first timeout, instant HOLD thereafter (v21.0)
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

    FAIL_SAFE = {"decision": "HOLD", "confidence": 0.500, "reasoning": "Fail-safe neutral -> endpoint unavailable."}

    def __init__(self, endpoint: str = LOCAL_ENDPOINT):
        self.endpoint = endpoint

    def generate_with_budget(self, system_prompt: str, user_prompt: str, word_budget: int = 150) -> str:
        """
        Non-streaming request with strict word budget.
        Constitution: enable_thinking=True, keep_alive=-1.
        """
        global _OLLAMA_CIRCUIT_OPEN

        # SRE v21.0: Circuit Breaker Check -- instant return if breaker is tripped
        if _OLLAMA_CIRCUIT_OPEN:
            import logging
            logging.warning("[QWEN_ENGINE] Circuit breaker OPEN. Skipping Ollama call -> instant HOLD.")
            return "TIMEOUT"

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
            resp = requests.post(self.endpoint, json=payload, timeout=_OLLAMA_TIMEOUT_SEC)
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            # Respect word budget
            words = raw.split()
            if len(words) > word_budget:
                raw = " ".join(words[:word_budget])
            return raw
        except requests.exceptions.Timeout:
            # SRE v21.0: Trip the circuit breaker on first timeout
            _OLLAMA_CIRCUIT_OPEN = True
            import traceback
            logging.error(
                f"[QWEN_ENGINE] [CIRCUIT_BREAKER_TRIPPED] Ollama timed out after "
                f"{_OLLAMA_TIMEOUT_SEC}s. Breaker is now OPEN. Traceback:\n{traceback.format_exc()}"
            )
            return "TIMEOUT"
        except requests.exceptions.ConnectionError:
            # Connection refused (Ollama not running) - trip breaker immediately
            _OLLAMA_CIRCUIT_OPEN = True
            import traceback
            logging.error(
                f"[QWEN_ENGINE] [CIRCUIT_BREAKER_TRIPPED] Ollama connection refused. "
                f"Breaker OPEN. Traceback:\n{traceback.format_exc()}"
            )
            return "TIMEOUT"
        except Exception as e:
            import traceback
            logging.error(f"[QWEN_ENGINE] Unexpected error during generation: {traceback.format_exc()}")
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
            except Exception as e:
                import traceback
                logging.debug(f"[QWEN_ENGINE] JSON parse/validate failed: {traceback.format_exc()}")
                pass

        return self.FAIL_SAFE