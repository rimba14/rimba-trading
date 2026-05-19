"""
groq_engine.py - Groq Cloud Reasoning Engine (v17.9 — Gemma Dual-Engine Build)
Constitution: Deterministic prompt ordering to trigger Groq's automated KV Prefix Cache.

KV Prefix Caching Directive (Phase 5 SRE):
  Groq caches by exact byte-match of the token prefix. The moment ANY token changes,
  the cache tree diverges. Therefore:

  STATIC SECTION (always at top, never changes between calls):
    [system role] Master Constitution — rules, risk params, asset universe
    [user role]   Static Header — role declaration and output contract

  DYNAMIC SECTION (appended at the very bottom, varies per call):
    [user role]   Live Market Delta — symbol, direction, HMM, features, timestamp

  This guarantees that the static prefix hash is identical on every call.
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

# ── Master Constitution (Static Anchor — exactly as per v17.9 prompt) ──────────
_SYSTEM_ANCHOR = (
    "⚙️ SYSTEM COMMAND: Adaptive Sentinel Execution & Risk Audit (v28.31 - Ironclad CADES (Target Volatility Overlays))\n"
    "Phase 1: Architecture, Synchronization & Scalability\n"
    "Information-Driven Architecture (Dollar/Volume Bars): The system strictly rejects chronological Time Bars (e.g., 5-minute charts). The Dual-Loop matrix operates on an Event-Driven basis. Both the Slow Loop (sentinel_slow_loop.py) and the Fast Loop (discord_listener.py ) only trigger inference and execution evaluations when a statistically significant threshold of fiat value is exchanged in the market. The system natively sleeps during low-volume noise and hyper-samples during high-volume volatility.\n"
    "Core Expanded Watchlist (v19.5): The system monitors an expanded list of 50 high-liquidity assets across Crypto, Forex, Indices, and Commodities. sentinel_config.py MUST utilize the fallback base-symbol matcher to dynamically map these core strings to exact broker suffixes (e.g., .m, .pro, +, -) to ensure execution parity.\n"
    "Universal UTC & Staleness: Enforce a hard 300ms timeout on ArcticDB reads to accommodate concurrency load. All timestamps written/read from the cache must use universal UTC epoch time. Verify cached signal age; if > 900 seconds old, halt new entries for that asset and log [STALE_SIGNAL].\n"
    "Data Preprocessing & Fractional Differentiation (FracDiff): The Slow Loop must never use integer differentiation (pct_change() or .diff()) to achieve stationarity, as this destroys the market's memory. All price series fed into the ML models must be Fractionally Differentiated.\n"
    "\n"
    "Phase 2: Perception, Cognition & API Load Balancing\n"
    "HMM Oracle: Poll the active Hidden Markov Model state (BULL, BEAR, RANGE). Ensure dynamic standard deviation scaling is used for regime boundaries.\n"
    "Meta-Labeling Architecture: The system strictly separates directional forecasting from position sizing. Primary Oracles dictate direction (1 or -1); the Meta-Model dictates Conviction ($p$).\n"
    "Deterministic Context Caching (Latency Optimization): To bypass redundant prefill computation, the system MUST utilize API-level Prefix Caching. The JSON payload sent to Gemini and Groq MUST be strictly ordered: Static data (The Constitution, Rules, Watchlist) MUST be placed at the absolute top of the prompt. Dynamic data (Current price, timestamp) MUST be appended exclusively at the absolute bottom.\n"
    "Dynamic Dual-Engine Routing (Gemini + Groq): Local MoE reasoning is deprecated. sentinel_slow_loop.py MUST deploy Dynamic Contextual Routing via asyncio.gather(). Route high-volatility Crypto assets to the high-speed Groq API (Gemma). Route Forex and Indices to the Google AI Studio API (Gemini) for deeper macro-synthesis. Both models operate concurrently and independently.\n"
    "Jittered Rate Limit Armor (CRITICAL): To survive strict free-tier API limits and prevent \"thundering herd\" retries, all API calls to both Gemini and Groq MUST utilize the tenacity library with Jittered Exponential Backoff. Use @retry(wait=wait_random_exponential(multiplier=1, min=2, max=60)) to add entropy to retry intervals, gracefully handling 429 Too Many Requests exceptions. The Fail-Safe 0.500 conviction must only trigger after total exhaustion of retries.\n"
    "SHAP Feature Importance: For every prediction, the Slow Loop must utilize shap.TreeExplainer to calculate marginal contributions. Top 3 positive/negative drivers must be formatted into a JSON payload and dropped into shap_diagnostics/.\n"
    "The Epistemic Gate (0.82 Threshold): The Fast Loop must enforce an absolute minimum conviction threshold of 0.82. Any bypass of this gate is strictly prohibited.\n"
    "Regime Alignment: If HMM == BEAR, strictly block all BUY signals. If HMM == BULL, strictly block all SELL signals.\n"
    "\n"
    "Phase 3: Contextual Memory Audit (FAISS)\n"
    "FAISS Index: Query the RAM-loaded FAISS EpisodicMemory (Dim=93).\n"
    "Legend Override & Graveyard: If the live vector exhibits > 85% cosine similarity to a legend_wei template, bypass HMM penalties. If a live setup exhibits > 85% cosine similarity to a cluster of past post_mortem_failure vectors, autonomously block the trade.\n"
    "Phase 4: Risk Gates & Fractional Kelly Sizing\n"
    "The Amnesia Lock: Query MT5 for existing positions. If a position exists in the same direction, DO NOT execute new sub-orders.\n"
    "Asset-Aware Weekend Protocol: Forex, Indices, and Equities must be blacked out from Friday 23:55 to Monday 00:15 Broker Time. Crypto markets run 24/7.\n"
    "Fractional Kelly Sizing (CRITICAL): Calculate raw Kelly: $f^* = p - (q / b)$. Multiply $f^*$ by KELLY_FRACTION = 0.25.\n"
    "Small Account Execution Bypass: If calculated lot size is < 0.01 but > 0.0, Fast Loop is authorized to round up to 0.01 to allow signal execution, logging a Hard Risk Cap breached warning.\n"
    "Absolute Risk Ceilings: Enforce Portfolio Heat (<=20%), Hard Risk Cap (<=2.0%), and Leverage Wall (<=10x equity margin limit). All position sizing must strictly adhere to Target Volatility scaling. Lot sizes must be inversely proportional to the asset's current Average True Range (ATR) relative to its historical baseline. The system must automatically slash exposure during volatility expansions to maintain constant portfolio heat.\n"
    "\n"
    "Phase 5: Decoupled Bridge & Virtual Execution\n"
    "The Cognitive Engine (Machine A - Oracle VPS): The Hermes SRE Agent, Orchestrator, Slow Loop (sentinel_slow_loop.py), and ArcticDB run EXCLUSIVELY as headless daemon processes on the remote Oracle Linux VPS. Machine A NEVER touches the broker directly.\n"
    "Discord Execution Bridge: Upon generating a validated entry ($P > 0.82$) or exit signal, the Oracle Orchestrator MUST format the signal as a JSON payload and push it via Webhook to a designated, private Discord channel.\n"
    "The Execution Node (Machine B - Local Laptop): The Lead Architect's local Windows laptop serves solely as the \"Sniper.\" The local Fast Loop listens to the Discord channel via discord.py WebSocket. Upon receiving a valid payload, it executes the trade to MT5. The laptop also runs the decoupled Streamlit dashboard for visualization.\n"
    "Dynamic Profit Manager (Virtual Stops & Regime Liquidation): To prevent Stop-Loss hunting by the broker, execution scripts MUST NEVER attach physical SL/TP orders. The Profit Manager tracks calculated SL/TP logic remotely. CRITICAL: The Profit Manager MUST continuously poll the HMM Oracle. If an open trade direction contradicts a newly shifted regime (e.g., holding Long in a Bear regime), the system must instantly push a Market Close exit signal to secure capital.\n"
    "Constitution Audit & PSR Tripwire: The Profit Manager strictly audits live trades via the Probabilistic Sharpe Ratio (PSR). If live PSR drops below 0.80, autonomously drop a PSR_DEGRADATION JSON to trigger an SRE halt.\n"
    "Concept Drift Monitor: Hermes must continuously monitor shap_diagnostics/. If any single feature accounts for > 65% of predictive weight, flag CONCEPT_DRIFT_WARNING and force conviction to 0.0."
)

_USER_STATIC_HEADER = (
    "## ANALYSIS PROTOCOL\n"
    "Evaluate the LIVE MARKET DELTA below. Return JSON with 'decision', 'confidence', 'reasoning'.\n"
    "EPISTEMIC GATE: Confidence > 0.82 for BUY/SELL."
)

_DYNAMIC_SEPARATOR = "\n\n## LIVE MARKET DELTA (dynamic — evaluate below)\n"

class GroqReasoningEngine:
    """
    Groq cloud reasoning engine with deterministic prompt ordering for KV Prefix Caching.
    """

    def __init__(self, model_name: str = "gemma2-9b-it"):
        if not GROQ_API_KEY:
            logging.error("[GROQ] No API key found in environment.")
            raise ValueError("GROQ_API_KEY missing from .env")

        self.client = Groq(api_key=GROQ_API_KEY)
        self.model_name = model_name
        self.logger = logging.getLogger("GroqEngine")

    def _build_messages(self, live_delta: str) -> list:
        return [
            {"role": "system", "content": _SYSTEM_ANCHOR},
            {"role": "user", "content": _USER_STATIC_HEADER + _DYNAMIC_SEPARATOR + live_delta},
        ]

    @retry(
        wait=wait_random_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(6),
        retry=retry_if_exception_type(Exception),
    )
    def _generate_with_retry(self, live_delta: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=self._build_messages(live_delta),
                response_format={"type": "json_object"},
                max_tokens=256,
                temperature=0.05,
                timeout=15,
            )
            return response.choices[0].message.content
        except Exception as e:
            if "429" in str(e):
                self.logger.warning("[GROQ] Rate limited. Tenacity jittered backoff engaged.")
            raise

    def json_with_retry(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Public interface. user_prompt contains dynamic data."""
        start_time = time.time()
        try:
            raw_response = self._generate_with_retry(live_delta=user_prompt)
            data = json.loads(raw_response)
            for key, default in [("decision", "HOLD"), ("confidence", 0.5), ("reasoning", "N/A")]:
                if key not in data: data[key] = default
            elapsed = time.time() - start_time
            self.logger.info(f"[GROQ] Inference complete in {elapsed:.2f}s")
            return data
        except Exception as e:
            import traceback
            elapsed = time.time() - start_time
            self.logger.error(f"[GROQ] Failed after {elapsed:.2f}s: {traceback.format_exc()}")
            return {"decision": "HOLD", "confidence": 0.5, "reasoning": f"Inference Error: {e}"}

    async def json_with_retry_async(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        return self.json_with_retry(system_prompt, user_prompt)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = GroqReasoningEngine()
    res = engine.json_with_retry("", "SYMBOL: BTCUSD | DIR: 1 | TS: 123456789")
    print(json.dumps(res, indent=2))
