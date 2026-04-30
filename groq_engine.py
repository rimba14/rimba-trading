"""
groq_engine.py - Groq Cloud Reasoning Engine (v17.7 KV Prefix Cache Build)
Constitution: Deterministic prompt ordering to trigger Groq's automated KV Prefix Cache.

KV Prefix Caching Directive (Phase 5 SRE):
  Groq caches by exact byte-match of the token prefix. The moment ANY token changes,
  the cache tree diverges. Therefore:

  STATIC SECTION (always at top, never changes between calls):
    [system role] Master Constitution — rules, risk params, asset universe
    [user role]   Static Header — role declaration and output contract

  DYNAMIC SECTION (appended at the very bottom, varies per call):
    [user role]   Live Market Delta — symbol, direction, HMM, features, timestamp

  This guarantees that the static prefix hash is identical on every call,
  allowing Groq to serve it from L2 KV cache and bill only the dynamic tokens.
"""

import os
import json
import logging
import time
from typing import Dict, Any

from groq import Groq
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ── Static Prefix Anchors (NEVER modify order or content without invalidating cache) ──
#
# These strings are assembled into message[0] (system) and message[1] (user-static).
# They must be 100% deterministic — no f-strings, no datetime.now(), no random seeds.
# Any mutation here breaks the KV prefix cache for ALL subsequent calls that session.

_SYSTEM_ANCHOR = (
    "You are the Sentinel Meta-Model, the high-speed reasoning core of the Adaptive "
    "Sentinel v17.7 Dual-Engine Cloud Architecture. Your role is momentum and volume "
    "analysis for Crypto and Metal assets.\n\n"
    "## CONSTITUTIONAL RULES (IMMUTABLE)\n"
    "1. EPISTEMIC GATE: Recommend BUY or SELL ONLY when confidence exceeds 0.82. "
    "   Below this threshold output HOLD without exception.\n"
    "2. REGIME ALIGNMENT: BUY is forbidden in BEAR regime. SELL is forbidden in BULL regime.\n"
    "3. OUTPUT CONTRACT: Return ONLY a valid JSON object with exactly three keys:\n"
    "   - \"decision\": one of \"BUY\", \"SELL\", or \"HOLD\" (uppercase string)\n"
    "   - \"confidence\": float 0.0–1.0 representing conviction strength\n"
    "   - \"reasoning\": concise string (≤ 80 words) naming the primary driver\n"
    "4. RISK CONSTITUTION: Kelly Fraction=0.25 | Hard risk cap=2% equity | "
    "   Max portfolio heat=20% | Leverage wall=10x.\n"
    "5. ASSET UNIVERSE (Crypto/Metal Stream): BTCUSD, ETHUSD, XAUUSD, XAGUSD, NAS100, SP500.\n"
    "6. FAIL-SAFE: Ambiguous or incomplete data → output HOLD, confidence=0.5."
)

_USER_STATIC_HEADER = (
    "## ANALYSIS PROTOCOL\n"
    "You will receive a LIVE MARKET DELTA block at the end of this message. "
    "The delta contains the symbol, primary statistical direction, HMM regime state, "
    "Kronos conviction score, ATR, volatility percentage, and a feature vector. "
    "Synthesise a high-speed momentum decision. "
    "Do NOT hallucinate price levels. Do NOT use information outside the provided features."
)

# Separator between static header and dynamic delta — must be an exact constant string
_DYNAMIC_SEPARATOR = "\n\n## LIVE MARKET DELTA (dynamic — evaluate below)\n"


class GroqReasoningEngine:
    """
    Groq cloud reasoning engine with deterministic prompt ordering for KV Prefix Caching.

    Prompt assembly layout:
      messages[0] = {role: system,  content: _SYSTEM_ANCHOR}          ← 100% static
      messages[1] = {role: user,    content: _USER_STATIC_HEADER      ← 100% static
                                              + _DYNAMIC_SEPARATOR
                                              + <live_delta>}          ← only this varies
    """

    def __init__(self, model_name: str = "llama-3.1-8b-instant"):
        if not GROQ_API_KEY:
            logging.error("[GROQ] No API key found in environment.")
            raise ValueError("GROQ_API_KEY missing from .env")

        self.client     = Groq(api_key=GROQ_API_KEY)
        self.model_name = model_name
        self.logger     = logging.getLogger("GroqEngine")

    # ── Prompt Builder ────────────────────────────────────────────────────────

    @staticmethod
    def _build_messages(live_delta: str) -> list:
        """
        Assembles the message list with strict static-to-dynamic ordering.

        CRITICAL CACHE CONTRACT:
          messages[0] (system) — fully static → always cache-hits
          messages[1] (user)   — static header + separator + live_delta
                                 The prefix of message[1] is also static, so Groq
                                 can cache-hit up to the separator boundary.
          The live_delta (symbol, timestamp, features) is ALWAYS appended LAST.
        """
        return [
            # ── Layer 0: Static system anchor (cache prefix root) ─────────────
            {
                "role": "system",
                "content": _SYSTEM_ANCHOR,
            },
            # ── Layer 1: Static user header + dynamic delta at the bottom ─────
            {
                "role": "user",
                "content": (
                    _USER_STATIC_HEADER       # static — matches cache prefix
                    + _DYNAMIC_SEPARATOR      # constant separator — matches cache prefix
                    + live_delta              # dynamic — only this breaks cache boundary
                ),
            },
        ]

    # ── Inference ─────────────────────────────────────────────────────────────

    @retry(
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        retry=retry_if_exception_type(Exception),
    )
    def _generate_with_retry(self, live_delta: str) -> str:
        """
        Core inference call. Messages are assembled via _build_messages() to ensure
        deterministic prefix ordering for Groq's automated KV cache.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=self._build_messages(live_delta),
                response_format={"type": "json_object"},
                max_tokens=256,
                temperature=0.05,   # Near-zero temp = deterministic output = better caching
                timeout=15,
            )
            # Log cache metrics if available in the response headers/usage
            usage = getattr(response, "usage", None)
            if usage:
                prompt_tokens = getattr(usage, "prompt_tokens", "?")
                cached_tokens = getattr(usage, "prompt_tokens_details", None)
                if cached_tokens:
                    self.logger.debug(
                        f"[GROQ_CACHE] Prompt tokens: {prompt_tokens} | "
                        f"Cache details: {cached_tokens}"
                    )
            return response.choices[0].message.content
        except Exception as e:
            if "429" in str(e) or "Rate limit" in str(e):
                self.logger.warning("[GROQ] Rate limited. Jittered backoff triggered.")
            raise

    # ── Public Interface ──────────────────────────────────────────────────────

    def json_with_retry(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        External interface (API-compatible with slow loop).

        `system_prompt` is accepted but ignored — the cached _SYSTEM_ANCHOR supersedes it.
        `user_prompt` is treated as the live_delta and appended at the bottom of
        the deterministic message chain to preserve the KV prefix cache boundary.
        """
        start_time = time.time()
        try:
            # user_prompt IS the live delta — it goes exclusively at the bottom
            raw_response = self._generate_with_retry(live_delta=user_prompt)
            data = json.loads(raw_response)

            if "confidence" not in data:  data["confidence"] = 0.5
            if "reasoning"  not in data:  data["reasoning"]  = "No reasoning provided."
            if "decision"   not in data:  data["decision"]   = "HOLD"

            elapsed = time.time() - start_time
            self.logger.info(f"[GROQ] Inference complete in {elapsed:.2f}s")
            return data

        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(f"[GROQ] Failed after {elapsed:.2f}s: {e}")
            return {"decision": "HOLD", "confidence": 0.5, "reasoning": f"Inference Error: {e}"}

    async def json_with_retry_async(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Async shim for the slow loop's thread-pool executor."""
        return self.json_with_retry(system_prompt, user_prompt)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = GroqReasoningEngine()
    test_res = engine.json_with_retry(
        system_prompt="",   # Superseded by _SYSTEM_ANCHOR
        user_prompt=(
            "SYMBOL: BTCUSD | PRIMARY_DIR: -1 | HMM: BEAR (p=0.511) | "
            "Kronos=0.147 | ATR=318.29 | Vol%=0.74 | "
            "FEATURES: {\"rsi\": 38.2, \"macd\": -142.5, \"ema_diff\": -0.0031}"
        ),
    )
    print(json.dumps(test_res, indent=2))
