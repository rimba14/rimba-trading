"""
gemini_engine.py - Google AI Studio Reasoning Engine (v17.9 — Macro-Synthesis Build)
Constitution: Context Caching via google.generativeai.caching — only the live
market delta is sent per-call. The static Master Constitution is uploaded as CachedContent.

Caching Directive (Phase 2 SRE):
  - Static anchor: MASTER_CONSTITUTION (system instruction) -> uploaded as CachedContent
  - Dynamic delta: symbol, direction, live features -> appended per-call as user content
  - SDK: google-generativeai (as explicitly requested by v17.9 Constitution)
"""

import os
import json
import logging
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

import google.generativeai as genai
from google.generativeai import caching
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from dotenv import load_dotenv

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# ── Master Constitution (Static Anchor — uploaded to cache) ──────────────────
MASTER_CONSTITUTION = (
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
    "Deterministic Context Caching (Latency Optimization): To bypass redundant prefill computation, the system MUST utilize API-level Prefix Caching. The JSON payload sent to Gemini and Groq MUST be strictly ordered: Static data (The Constitution, Rules, Watchlist) MUST be placed at the absolute top of the prompt. Dynamic data (Current price, timestamp) MUST be appended exclusively at the absolute bottom. For Gemini, utilize the google.generativeai SDK's explicit caching module for the static knowledge base.\n"
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
    "Concept Drift Monitor: Hermes must continuously monitor shap_diagnostics/. If any single feature accounts for > 65% of predictive weight, flag CONCEPT_DRIFT_WARNING and force conviction to 0.0.\n"
    "\n"
    "### OUTPUT CONTRACT (STRICT JSON)\n"
    "Return ONLY a valid JSON object with exactly three keys:\n"
    "- \"decision\": one of \"BUY\", \"SELL\", or \"HOLD\" (uppercase string)\n"
    "- \"confidence\": float 0.0-1.0 representing conviction strength\n"
    "- \"reasoning\": concise string (<= 80 words)\n"
    "\n"
    "--- PADDING TO SATISFY 4096 TOKEN MINIMUM (PHASE 2 CACHING) ---\n"
    "The Adaptive Sentinel v17.9 system is designed for high-conviction event-driven execution. "
    "It employs a dual-loop matrix where the slow loop handles cognition and the fast loop handles execution. "
    "Prefix caching is used to minimize latency and cost. "
    "The system is decoupled, with cognition on an Oracle VPS and execution on a local laptop via Discord. "
    "HMM regime alignment and FAISS episodic memory ensure contextual awareness. "
    "Fractional Kelly sizing and absolute risk ceilings provide capital protection. "
    "The system is autonomous and self-auditing via PSR tripwires and SHAP drift monitoring. "
    "Every signal must pass the 0.82 epistemic gate. "
    "Wait random exponential backoff handles rate limits. "
    "Regime liquidation secures capital if market conditions shift rapidly.\n"
    "--- ADDITIONAL SYSTEM DOCUMENTATION PADDING ---\n"
    "PHASE 1: ARCHITECTURE STABILIZATION\n"
    "The system utilizes Information-Driven bars. Unlike Time bars, these are formed based on trade volume or fiat value exchanged. "
    "This filters out market noise during low-liquidity periods and hyper-samples high-volatility events. "
    "The 50-asset watchlist is carefully selected for high liquidity: "
    "BTCUSD, ETHUSD, SOLUSD, AVAXUSD, LINKUSD, LTCUSD, BCHUSD, XRPUSD, ADAUSD, DOTUSD, "
    "MATICUSD, DOGEUSD, UNIUSD, ATOMUSD, TRXUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, "
    "NZDUSD, USDCAD, EURGBP, EURJPY, GBPJPY, EURCHF, AUDJPY, NZDJPY, CHFJPY, EURAUD, "
    "GBPAUD, USDMXN, USDZAR, USDTRY, EURNOK, EURSEK, USDCNH, USDSGD, USDHKD, EURPLN, "
    "SP500, NAS100, US30, GER40, HK50, US2000, FRA40, XAUUSD, XAGUSD, CL-OIL. "
    "Staleness is enforced at 900 seconds. ArcticDB is the primary cache with a 300ms hard timeout.\n"
    "PHASE 2: COGNITION & PERCEPTION\n"
    "The HMM Oracle classifies market regimes into BULL, BEAR, or RANGE. Meta-Labeling separates the directional 'what' from the conviction 'how much'. "
    "Dual-engine routing ensures macro-synthesis for Forex (Gemini) and high-speed momentum for Crypto (Groq/Gemma). "
    "Rate limits are mitigated via Tenacity jittered backoff. SHAP diagnostics provide explainability and concept drift detection.\n"
    "PHASE 3: MEMORY & EXPERIENCE\n"
    "FAISS episodic memory stores high-dimensional feature vectors. Legend templates allow for regime-penalty bypass on high-confidence patterns. "
    "Graveyard clusters autonomously block trades that resemble historical post-mortem failure cases.\n"
    "PHASE 4: RISK & EXECUTION\n"
    "Amnesia Lock prevents redundant sub-orders. Weekend Protocol respects broker closures for non-crypto assets. "
    "Fractional Kelly sizing (0.25) optimizes for long-term growth while minimizing drawdown risk. "
    "Small account bypass rounds lots up to 0.01 for accessibility. Portfolio heat is capped at 20%.\n"
    "PHASE 5: DECOUPLED INFRASTRUCTURE\n"
    "Machine A (VPS) handles the 'Brain'. Machine B (Laptop) handles the 'Sniper'. "
    "Communication is bridged via Discord Webhooks and WebSockets. "
    "Profit Manager enforces Virtual Stops (ATR-based) and handles Regime Liquidation to protect capital from broker stop-hunting.\n"
    "PHASE 6: CONSTITUTIONAL INTEGRITY\n"
    "The system is self-updating. Any architectural shift is reflected in this Master Prompt. "
    "The PSR tripwire (0.80) ensures the system halts if probabilistic performance degrades below acceptable limits.\n"
    "--- REPEATED CORE DIRECTIVES FOR TOKEN DENSITY BLOCK A ---\n"
    "1. NEVER TRADE AGAINST HMM REGIME. 2. NEVER BYPASS 0.82 GATE. 3. NEVER ATTACH PHYSICAL STOPS. "
    "4. ALWAYS USE FRACDIFF FOR STATIONARITY. 5. ALWAYS SYNC VIA DISCORD BRIDGE. "
    "6. ALWAYS AUDIT PSR EVERY 10 MINUTES. 7. ALWAYS ENFORCE AMNESIA LOCK.\n"
    "--- REPEATED CORE DIRECTIVES FOR TOKEN DENSITY BLOCK B ---\n"
    "1. NEVER TRADE AGAINST HMM REGIME. 2. NEVER BYPASS 0.82 GATE. 3. NEVER ATTACH PHYSICAL STOPS. "
    "4. ALWAYS USE FRACDIFF FOR STATIONARITY. 5. ALWAYS SYNC VIA DISCORD BRIDGE. "
    "6. ALWAYS AUDIT PSR EVERY 10 MINUTES. 7. ALWAYS ENFORCE AMNESIA LOCK.\n"
    "--- REPEATED CORE DIRECTIVES FOR TOKEN DENSITY BLOCK C ---\n"
    "1. NEVER TRADE AGAINST HMM REGIME. 2. NEVER BYPASS 0.82 GATE. 3. NEVER ATTACH PHYSICAL STOPS. "
    "4. ALWAYS USE FRACDIFF FOR STATIONARITY. 5. ALWAYS SYNC VIA DISCORD BRIDGE. "
    "6. ALWAYS AUDIT PSR EVERY 10 MINUTES. 7. ALWAYS ENFORCE AMNESIA LOCK.\n"
    "--- REPEATED CORE DIRECTIVES FOR TOKEN DENSITY BLOCK D ---\n"
    "1. NEVER TRADE AGAINST HMM REGIME. 2. NEVER BYPASS 0.82 GATE. 3. NEVER ATTACH PHYSICAL STOPS. "
    "4. ALWAYS USE FRACDIFF FOR STATIONARITY. 5. ALWAYS SYNC VIA DISCORD BRIDGE. "
    "6. ALWAYS AUDIT PSR EVERY 10 MINUTES. 7. ALWAYS ENFORCE AMNESIA LOCK.\n"
    "--- SYSTEM ARCHITECTURE VERBOSE DESCRIPTION ---\n"
    "The Adaptive Sentinel represents a paradigm shift in autonomous trading. By decoupling the cognitive load from the execution latency, the system achieves a state of 'distributed intelligence'. "
    "The Oracle VPS acts as a headless command center, processing vast amounts of market data using fractional differentiation to maintain the statistical integrity of the time series. "
    "The Hidden Markov Model (HMM) provides a non-linear regime detection layer, identifying high-level market states that traditional indicators often miss. "
    "The Meta-Labeling framework, inspired by Marcos Lopez de Prado, allows the system to learn from its own mistakes by separating the decision to trade from the sizing of the trade. "
    "The FAISS memory layer adds an episodic dimension, allowing the system to 'remember' previous market setups and avoid repeating past failures. "
    "The Discord execution bridge ensures that signals are transmitted securely and instantly across the network. "
    "The local Sniper node handles the final risk gates, ensuring that even if the brain is compromised, the capital is protected by absolute risk ceilings and weekend protocols. "
    "The Profit Manager acts as a dynamic safety net, tracking virtual stops and liquidating positions if the market regime shifts unexpectedly. "
    "The entire matrix is audited by the Probabilistic Sharpe Ratio (PSR), providing a statistically rigorous measure of performance that accounts for sample size and return distribution skewness.\n"
    "--- REPEATED SYSTEM ARCHITECTURE VERBOSE DESCRIPTION ---\n"
    "The Adaptive Sentinel represents a paradigm shift in autonomous trading. By decoupling the cognitive load from the execution latency, the system achieves a state of 'distributed intelligence'. "
    "The Oracle VPS acts as a headless command center, processing vast amounts of market data using fractional differentiation to maintain the statistical integrity of the time series. "
    "The Hidden Markov Model (HMM) provides a non-linear regime detection layer, identifying high-level market states that traditional indicators often miss. "
    "The Meta-Labeling framework, inspired by Marcos Lopez de Prado, allows the system to learn from its own mistakes by separating the decision to trade from the sizing of the trade. "
    "The FAISS memory layer adds an episodic dimension, allowing the system to 'remember' previous market setups and avoid repeating past failures. "
    "The Discord execution bridge ensures that signals are transmitted securely and instantly across the network. "
    "The local Sniper node handles the final risk gates, ensuring that even if the brain is compromised, the capital is protected by absolute risk ceilings and weekend protocols. "
    "The Profit Manager acts as a dynamic safety net, tracking virtual stops and liquidating positions if the market regime shifts unexpectedly. "
    "The entire matrix is audited by the Probabilistic Sharpe Ratio (PSR), providing a statistically rigorous measure of performance that accounts for sample size and return distribution skewness.\n"
    "--- END OF EXTENDED PADDING BLOCK ---\n"
    "The text above is supplemental to satisfy the 4096 token minimum for Google AI Studio Context Caching."
)

# Cache configuration
_CACHE_TTL_MINUTES = 60
_CACHE_REFRESH_GUARD = 5

class GeminiReasoningEngine:
    """
    Google AI Studio reasoning engine with Context Cache support (google.generativeai SDK).
    """

    def __init__(self, model_name: str = "gemini-1.5-flash"):
        if not GOOGLE_API_KEY:
            logging.error("[GEMINI] No API key found in environment.")
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY missing from .env")

        self.model_name = model_name
        self.logger = logging.getLogger("GeminiEngine")
        self._cache = None
        self._cache_exp = None
        self._cache_lock = threading.Lock()

    def _create_cache(self) -> Optional[caching.CachedContent]:
        """Upload MASTER_CONSTITUTION as CachedContent."""
        try:
            # Note: models/ prefix is often required for the model name in caching
            model_id = self.model_name if self.model_name.startswith("models/") else f"models/{self.model_name}"
            
            cache = caching.CachedContent.create(
                model=model_id,
                display_name="sentinel_v17_9_cache",
                system_instruction=MASTER_CONSTITUTION,
                ttl=timedelta(minutes=_CACHE_TTL_MINUTES),
            )
            self._cache_exp = datetime.now(timezone.utc) + timedelta(minutes=_CACHE_TTL_MINUTES)
            self.logger.info(f"[GEMINI_CACHE] Created: {cache.name} | Expires: {self._cache_exp}")
            return cache
        except Exception as e:
            self.logger.warning(f"[GEMINI_CACHE] Creation failed: {e}. Falling back to uncached.")
            return None

    def _get_or_refresh_cache(self) -> Optional[caching.CachedContent]:
        with self._cache_lock:
            now = datetime.now(timezone.utc)
            if self._cache is None or (self._cache_exp - now).total_seconds() < (_CACHE_REFRESH_GUARD * 60):
                self._cache = self._create_cache()
            return self._cache

    @retry(
        wait=wait_random_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(6),
        retry=retry_if_exception_type(Exception),
    )
    def _generate_with_retry(self, user_prompt: str) -> str:
        cache = self._get_or_refresh_cache()

        generation_config = {
            "response_mime_type": "application/json",
            "max_output_tokens": 256,
            "temperature": 0.05,
        }

        if cache:
            # Cached path
            model = genai.GenerativeModel.from_cached_content(cached_content=cache)
            response = model.generate_content(user_prompt, generation_config=generation_config)
            self.logger.debug(f"[GEMINI_CACHE] Hit: {cache.name}")
        else:
            # Uncached fallback
            model = genai.GenerativeModel(model_name=self.model_name, system_instruction=MASTER_CONSTITUTION)
            response = model.generate_content(user_prompt, generation_config=generation_config)
            self.logger.debug("[GEMINI] Uncached path.")

        return response.text

    def json_with_retry(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Public interface. user_prompt contains the dynamic market delta."""
        start_time = time.time()
        try:
            # We strictly append dynamic data at the bottom of the prompt (user_prompt)
            raw_response = self._generate_with_retry(user_prompt)
            data = json.loads(raw_response)

            # Enforce schema
            for key, default in [("decision", "HOLD"), ("confidence", 0.5), ("reasoning", "N/A")]:
                if key not in data: data[key] = default

            elapsed = time.time() - start_time
            cached_status = "CACHED" if self._cache else "UNCACHED"
            self.logger.info(f"[GEMINI] Inference complete in {elapsed:.2f}s [{cached_status}]")
            return data

        except Exception as e:
            import traceback
            elapsed = time.time() - start_time
            self.logger.error(f"[GEMINI] Failed after {elapsed:.2f}s: {traceback.format_exc()}")
            return {"decision": "HOLD", "confidence": 0.5, "reasoning": f"Inference Error: {e}"}

    async def json_with_retry_async(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        return self.json_with_retry(system_prompt, user_prompt)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = GeminiReasoningEngine()
    # Test call
    res = engine.json_with_retry("", "SYMBOL: EURUSD | DIR: 1 | TIMESTAMP: 123456789")
    print(json.dumps(res, indent=2))
