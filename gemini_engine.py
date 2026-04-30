"""
gemini_engine.py - Google AI Studio Reasoning Engine (v17.7 Context Cache Build)
Constitution: Context Caching via CachedContent API — only delta (live market state)
is sent per-call. The static Master Constitution is uploaded ONCE per session.

Caching Directive (Phase 5 SRE):
  - Static anchor: MASTER_CONSTITUTION (system prompt) → uploaded as CachedContent
  - Dynamic delta: symbol, direction, live features → appended per-call as user prompt
  - TTL: 60 minutes (auto-refreshed if within 5-minute expiry window)
  - Fallback: uncached path if cache creation fails (e.g. key lacks caching scope)
"""

import os
import json
import logging
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

import google.generativeai as genai
from google.generativeai import caching as genai_caching
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from dotenv import load_dotenv

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

# ── Master Constitution (Static Anchor — uploaded once to cache) ──────────────
# This string is the prefix that NEVER changes between calls.
# Placing all static rules here maximises the cached token ratio.
MASTER_CONSTITUTION = (
    "You are the Sentinel Meta-Model, the reasoning core of the Adaptive Sentinel v17.7 "
    "Dual-Engine Cloud Architecture. Your role is deep macro-synthesis for Forex and Index assets.\n\n"
    "## CONSTITUTIONAL RULES (IMMUTABLE)\n"
    "1. EPISTEMIC GATE: You must only recommend BUY or SELL when your internal confidence exceeds 0.82. "
    "   Below this threshold you MUST output HOLD.\n"
    "2. REGIME ALIGNMENT: Never recommend BUY in a confirmed BEAR regime. "
    "   Never recommend SELL in a confirmed BULL regime. Honour the HMM state.\n"
    "3. OUTPUT CONTRACT: You MUST return ONLY a single valid JSON object with exactly three keys:\n"
    "   - \"decision\": one of \"BUY\", \"SELL\", or \"HOLD\" (string, uppercase)\n"
    "   - \"confidence\": a float between 0.0 and 1.0 representing your conviction\n"
    "   - \"reasoning\": a concise string (≤ 80 words) explaining the primary driver\n"
    "4. RISK CONSTITUTION: Kelly Fraction = 0.25. Hard risk cap per trade = 2% of equity. "
    "   Maximum portfolio heat = 20%. Leverage wall = 10×.\n"
    "5. ASSET UNIVERSE (Forex/Index Stream): EURUSD, USDJPY, GBPUSD, AUDUSD, USDCHF, NZDUSD, GER40.\n"
    "6. FAIL-SAFE: If market data is ambiguous, incomplete, or contradictory, output HOLD with "
    "   confidence 0.5. Never speculate beyond the provided features.\n\n"
    "You will receive a live market delta containing the symbol, HMM regime, Kronos conviction, "
    "and a feature vector. Synthesise a macro-informed trading decision."
)

# Cache TTL configuration
_CACHE_TTL_MINUTES   = 60
_CACHE_REFRESH_GUARD = 5   # Refresh if less than this many minutes remain


class GeminiReasoningEngine:
    """
    Google AI Studio reasoning engine with Context Cache support.

    On first call, the MASTER_CONSTITUTION is uploaded as a CachedContent object.
    All subsequent calls reference only the cache name + live market delta,
    dramatically reducing input token consumption and latency.
    """

    def __init__(self, model_name: str = "models/gemini-2.5-flash-preview-04-17"):
        if not GOOGLE_API_KEY:
            logging.error("[GEMINI] No API key found in environment.")
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY missing from .env")

        genai.configure(api_key=GOOGLE_API_KEY)
        self.model_name  = model_name
        self.logger      = logging.getLogger("GeminiEngine")
        self._cache      = None          # CachedContent object
        self._cache_exp  = None          # datetime when cache expires (UTC)
        self._cache_lock = threading.Lock()  # Thread-safe cache init

    # ── Cache Lifecycle ───────────────────────────────────────────────────────

    def _create_cache(self) -> Optional[object]:
        """
        Upload MASTER_CONSTITUTION to Google's Context Cache API.
        Returns the CachedContent object, or None if caching is unavailable.

        The cache is pinned to a specific model version (non-'-latest' alias)
        because the Caching API requires an exact, stable model name.
        """
        try:
            ttl_seconds = _CACHE_TTL_MINUTES * 60
            cache = genai_caching.CachedContent.create(
                model=self.model_name,
                display_name="sentinel_master_constitution",
                system_instruction=MASTER_CONSTITUTION,
                contents=[],          # No static user-turn content; constitution is system-only
                ttl=timedelta(seconds=ttl_seconds),
            )
            expiry_utc = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            self.logger.info(
                f"[GEMINI_CACHE] CachedContent created: {cache.name} | "
                f"TTL={_CACHE_TTL_MINUTES}min | Expires: {expiry_utc.strftime('%H:%M:%S UTC')}"
            )
            return cache, expiry_utc
        except Exception as e:
            self.logger.warning(
                f"[GEMINI_CACHE] Cache creation failed — falling back to uncached path. "
                f"Reason: {e}"
            )
            return None, None

    def _get_or_refresh_cache(self):
        """
        Thread-safe accessor. Returns the active CachedContent object.
        Automatically refreshes if the cache is within _CACHE_REFRESH_GUARD minutes of expiry.
        """
        with self._cache_lock:
            now = datetime.now(timezone.utc)
            refresh_threshold = now + timedelta(minutes=_CACHE_REFRESH_GUARD)

            # First init or near-expiry refresh
            if self._cache is None or (self._cache_exp and self._cache_exp <= refresh_threshold):
                self.logger.info("[GEMINI_CACHE] Initialising / refreshing CachedContent...")
                self._cache, self._cache_exp = self._create_cache()

            return self._cache

    # ── Inference ─────────────────────────────────────────────────────────────

    @retry(
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        retry=retry_if_exception_type(Exception),
    )
    def _generate_with_retry(self, user_prompt: str) -> str:
        """
        Core inference call. Uses CachedContent if available, otherwise falls back
        to a full-prompt uncached call. The user_prompt contains ONLY the live delta.
        """
        cache = self._get_or_refresh_cache()

        if cache is not None:
            # ── CACHED PATH: Pass only the live market delta ──────────────────
            # The model resolves the system instruction from the cache name.
            cached_model = genai.GenerativeModel.from_cached_content(cached_content=cache)
            response = cached_model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                    max_output_tokens=256,
                    temperature=0.05,
                ),
                request_options={"timeout": 15},
            )
            self.logger.debug(f"[GEMINI_CACHE] Cache hit: {cache.name}")
        else:
            # ── FALLBACK PATH: Full prompt (no caching) ───────────────────────
            full_prompt = f"{MASTER_CONSTITUTION}\n\n{user_prompt}"
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                    max_output_tokens=256,
                    temperature=0.05,
                ),
                request_options={"timeout": 15},
            )
            self.logger.debug("[GEMINI_CACHE] Cache miss — uncached fallback used.")

        return response.text

    # ── Public Interface ──────────────────────────────────────────────────────

    def json_with_retry(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        External interface. `system_prompt` is accepted for API compatibility
        but is superseded by the cached MASTER_CONSTITUTION. Only `user_prompt`
        (the live market delta) is sent over the wire on each call.
        """
        start_time = time.time()
        try:
            raw_response = self._generate_with_retry(user_prompt)
            data = json.loads(raw_response)

            if "confidence" not in data:  data["confidence"] = 0.5
            if "reasoning"  not in data:  data["reasoning"]  = "No reasoning provided."
            if "decision"   not in data:  data["decision"]   = "HOLD"

            elapsed = time.time() - start_time
            cached  = "CACHED" if self._cache else "UNCACHED"
            self.logger.info(f"[GEMINI] Inference complete in {elapsed:.2f}s [{cached}]")
            return data

        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(f"[GEMINI] Failed after {elapsed:.2f}s: {e}")
            return {"decision": "HOLD", "confidence": 0.5, "reasoning": f"Inference Error: {e}"}

    async def json_with_retry_async(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Async shim for the slow loop's thread-pool executor."""
        return self.json_with_retry(system_prompt, user_prompt)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = GeminiReasoningEngine()
    test_res = engine.json_with_retry(
        system_prompt="",   # Superseded by MASTER_CONSTITUTION cache
        user_prompt=(
            "SYMBOL: EURUSD | PRIMARY_DIR: -1 | HMM: BULL (p=0.74) | "
            "Kronos=0.355 | ATR=0.00061 | Vol%=0.44"
        ),
    )
    print(json.dumps(test_res, indent=2))
