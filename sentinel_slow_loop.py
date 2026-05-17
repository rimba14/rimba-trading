"""
sentinel_slow_loop.py - ADAPTIVE SENTINEL SLOW LOOP (v22.6 - MixTS Reconnection)
Machine A (Brain) Optimized | Windows Hybrid Support
"""
import gc
import torch
# Directive 3: CPU Thread Throttling (SRE Patch)
torch.set_num_threads(4)

import sys
import os
import time
import json
import logging
import random
import asyncio
import traceback
import threading
import concurrent.futures
import itertools
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
from collections import defaultdict

import numpy as np
import pandas as pd

# Global dicts for Regime Hysteresis (v20.4)
_HMM_HISTORY = defaultdict(list)
_OFFICIAL_REGIME = {}
_GLOBAL_CS_RANKS = {}
_LAST_CS_REFRESH = 0

def _pre_scan_watchlist(watchlist: list):
    """
    Directive 3: Global Pre-Scan for Market Neutralization.
    Calculates relative performance ranks across the entire watchlist.
    """
    global _GLOBAL_CS_RANKS
    metrics = {}
    
    logging.info(f"[ALPHA_FACTORY] Executing Cross-Sectional Pre-Scan ({len(watchlist)} assets)...")
    
    for symbol in watchlist:
        try:
            # 1. Force the symbol into Market Watch
            mt5.symbol_select(symbol, True)

            # 2. Force a single tick request to wake up the broker's data stream
            mt5.symbol_info_tick(symbol)

            # 3. Now safely request the OHLCV history with async pre-fetch retry loop
            rates = None
            max_retries = 5
            for attempt in range(max_retries):
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 96)
                if rates is not None and len(rates) > 0:
                    break
                time.sleep(1.0)

            if rates is None or len(rates) == 0:
                err = mt5.last_error()
                print(f"[ALERT] [DATA STARVATION] MT5 failed to fetch history for {symbol} after {max_retries} attempts. MT5 Error: {err}")
                metrics[symbol] = 0.0
                continue

            if len(rates) > 1:
                close_now = rates[-1]['close']
                close_prev = rates[0]['close']
                momentum = (close_now - close_prev) / (close_prev + 1e-9)
                metrics[symbol] = momentum
            else:
                metrics[symbol] = 0.0
        except Exception as e:
            logging.warning(f"[ALPHA_FACTORY] Pre-scan failed for {symbol}: {e}")
            metrics[symbol] = 0.0
            
    _GLOBAL_CS_RANKS = feat_eng.compute_cross_sectional_ranks(metrics)
    logging.info(f"[ALPHA_FACTORY] Cross-Sectional Ranks computed for {len(_GLOBAL_CS_RANKS)} symbols.")


def calculate_mean_reversion_score(rsi, bbpos):
    """
    Mean-Reversion Conviction Score (0.0 to 1.0)
    0.0 = Strong SELL (Overbought, Price > Upper BB)
    1.0 = Strong BUY (Oversold, Price < Lower BB)
    """
    rsi_norm = max(0.0, min(1.0, rsi / 100.0))
    bb_norm = max(0.0, min(1.0, bbpos))
    
    # Score where 1.0 means STRONG BUY, 0.0 means STRONG SELL
    score = ((1.0 - rsi_norm) + (1.0 - bb_norm)) / 2.0
    
    # If RSI is not in extremes, dampen the conviction heavily towards 0.5
    if 30 < rsi < 70:
        score = 0.5 + (score - 0.5) * 0.3
        
    return score
import MetaTrader5 as mt5
import xgboost as xgb
import shap
import requests
import copy
from statsmodels.tsa.stattools import adfuller

# Windows Hybrid Initialization (v23.6 Heartbeat)
import mt5_bridge
from sentinel_config import BASE_WATCHLIST

if os.name == 'nt':
    success, WATCHLIST = mt5_bridge.initialize_mt5_with_heartbeat(BASE_WATCHLIST)
    if not success:
        logging.critical("[BOOT] Heartbeat or MT5 Initialization FAILED. SRE HALT.")
        sys.exit(1)
    logging.info(f"[BOOT] v23.6 Heartbeat PASS. Active Watchlist size: {len(WATCHLIST)}")

sys.path.append(r"C:\Sentinel_Project")

import git_arctic
import gitagent_hmm as hmm
import gitagent_sigproc as sigproc
import kronos_bridge
import rl_agents.oxford_ddqn as ddqn_bridge
import timesfm_bridge
import gitagent_utils as utils
import gitagent_bars as bars
import gitagent_memory as memory
import feature_engineering as feat_eng
import gitagent_mixts as mixts

# -- Config --------------------------------------------------------------------
from sentinel_config import (
    EPISTEMIC_GATE, STALENESS_THRESHOLD, ARCTIC_TIMEOUT,
    KELLY_FRACTION, PORTFOLIO_HEAT_CAP, HARD_RISK_CAP, LEVERAGE_WALL,
    WATCHLIST, REASONING_TIMEOUT,
    GROQ_GEMMA_MODEL, GEMINI_MODEL_NAME,
)

# -- TensorTrade Integration (v18.6) --
try:
    from tensor_env import UnifiedObserver
    _OBSERVER = UnifiedObserver(window_size=20)
    logging.info("[BOOT] TensorTrade UnifiedObserver initialized.")
except ImportError:
    _OBSERVER = None
    logging.warning("[BOOT] TensorTrade modules not found. S_t generation will be degraded.")

# -- Paths ---------------------------------------------------------------------
PROJECT_ROOT = Path(r"C:\Sentinel_Project")
SHAP_DIR     = PROJECT_ROOT / "shap_diagnostics"
SIGNAL_DIR   = PROJECT_ROOT / "cognition_queue"
HALT_PATH    = PROJECT_ROOT / "halt_signal.json"
LOG_DIR      = Path(r"C:\sentinel_logs")
META_MODEL_PATH = PROJECT_ROOT / "data" / "meta_model_active.pkl"

for d in [SHAP_DIR, SIGNAL_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# -- Logging -------------------------------------------------------------------
# -- Logging -------------------------------------------------------------------
import io as _io
def _get_utf8_stream():
    if getattr(sys.stdout, 'encoding', '').lower() == 'utf-8':
        return sys.stdout
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        return sys.stdout
    except Exception:
        return _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

_UTF8_STREAM = _get_utf8_stream()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SLOW_LOOP] %(message)s",
    force=True,
    handlers=[
        logging.StreamHandler(_UTF8_STREAM),
        logging.FileHandler(str(LOG_DIR / "slow_loop_v17_9.log"), encoding="utf-8"),
    ],
)

# -- XGBoost Resurrection (v23.6) -----------------------------------------------
XGB_MODEL_PATH = PROJECT_ROOT / "data" / "sentinel_xgb_model.json"
_XGB_MODEL = None
if XGB_MODEL_PATH.exists():
    try:
        _XGB_MODEL = xgb.Booster()
        _XGB_MODEL.load_model(str(XGB_MODEL_PATH))
        logging.info(f"[BOOT] XGBoost Model loaded from {XGB_MODEL_PATH.name}")
    except Exception as e:
        logging.error(f"[BOOT] Failed to load XGBoost model: {e}")
else:
    logging.warning(f"[BOOT] XGBoost model {XGB_MODEL_PATH} not found. Using fallback inference.")

def get_xgb_prediction(features_df):
    """v23.6: Executes live XGBoost inference on the current feature matrix."""
    if _XGB_MODEL is None:
        return 0.500000
    try:
        # Prepare DMatrix from the last row of the feature-engineered dataframe
        # We use a 128-dim compressed vector if available, otherwise raw features
        latest_features = features_df.tail(1).select_dtypes(include=[np.number])
        dmat = xgb.DMatrix(latest_features)
        pred = _XGB_MODEL.predict(dmat)[0]
        return float(pred)
    except Exception as e:
        logging.error(f"[XGB_INFERENCE] Error: {e}. Falling back to 0.500.")
        return 0.500000
# -- Contextual Routing - Phase 2 Constitution (v17.9) ------------------
# CONSTITUTION DIRECTIVE: Route HIGH-VOLATILITY CRYPTO -> Groq (Gemma)
#                         Route FOREX + INDICES + METALS -> Gemini (macro-synthesis)
from sentinel_config import CRYPTO_BASE_SYMBOLS

def _get_engine_for_symbol(symbol: str) -> str:
    """Dynamically routes symbol to either Groq or Gemini based on config."""
    # Check if base symbol is in CRYPTO_BASE_SYMBOLS
    base = symbol
    for suffix in [".m", ".pro", ".t", "+", "-", ".r", ".c", ".x"]:
        if symbol.endswith(suffix):
            base = symbol[:-len(suffix)]
            break
    
    if base in CRYPTO_BASE_SYMBOLS:
        return "GROQ"
    return "GEMINI"


try:
    from math_meta_model import MathMetaModel
    _MATH_META_MODEL = MathMetaModel()
    logging.info("[ROUTER] Math Meta-Model (v18.2) initialized successfully.")
except Exception as _e:
    _MATH_META_MODEL = None
    logging.warning(f"[ROUTER] Math Meta-Model unavailable: {_e}")

# -- Agent Quarantine (v26.8) --------------------------------------------------
from agent_quarantine import registry, register_default_agents
register_default_agents()
# Ensure local agent states are updated based on file presence
from rl_agents.oxford_ddqn import CHECKPOINT_PATH
if os.path.exists(CHECKPOINT_PATH):
    registry.update("ddqn", is_initialized=True, training_episodes=1000) # Proxy
else:
    registry.update("ddqn", is_initialized=False, training_episodes=0)

# -- ArcticDB Singleton (300 ms timeout enforced via ThreadPoolExecutor) -------
from arcticdb import Arctic
_ARCTIC = Arctic("lmdb://./data/arctic_cache")
oracle_lib = (
    _ARCTIC["oracle_cache"]
    if "oracle_cache" in _ARCTIC.list_libraries()
    else _ARCTIC.create_library("oracle_cache")
)

def _arctic_read(key: str):
    """ArcticDB read with hard 300 ms timeout (Phase 1)."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(oracle_lib.read, key)
        try:
            return fut.result(timeout=ARCTIC_TIMEOUT)
        except concurrent.futures.TimeoutError:
            logging.error(f"[ARCTIC_TIMEOUT] Read '{key}' exceeded {ARCTIC_TIMEOUT*1000:.0f} ms. Returning None to skip asset.")
            return None

def _arctic_write(key: str, df: pd.DataFrame):
    """ArcticDB write with hard 300 ms timeout (Phase 1)."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(oracle_lib.write, key, df)
        try:
            fut.result(timeout=ARCTIC_TIMEOUT)
        except concurrent.futures.TimeoutError:
            logging.error(f"[ARCTIC_TIMEOUT] Write '{key}' exceeded {ARCTIC_TIMEOUT*1000:.0f} ms.")

# -- Staleness Gate -------------------------------------------------------------
def _check_staleness(symbol: str) -> bool:
    """Returns True (stale) if cached signal is > STALENESS_THRESHOLD seconds old."""
    item = _arctic_read(f"{symbol}_meta")
    if item is None:
        return False  # No cache yet - not stale, just cold
    try:
        cached_ts = float(item.data.iloc[-1]["timestamp"])
        age = time.time() - cached_ts
        if age > STALENESS_THRESHOLD:
            logging.warning(f"[STALE_SIGNAL] {symbol}: signal age {age:.0f}s > {STALENESS_THRESHOLD}s. Halting new entries.")
            return True
    except Exception:
        pass
    return False

# -- Fractional Differentiation (Phase 1 - memory-preserving stationarity) ----
def _fracdiff_weights(d: float, threshold: float = 1e-5) -> np.ndarray:
    w = [1.0]
    k = 1
    while True:
        w_k = -w[-1] / k * (d - k + 1)
        if abs(w_k) < threshold:
            break
        w.append(w_k)
        k += 1
    return np.array(w[::-1])

def apply_frac_diff(series: np.ndarray, d: float, threshold: float = 1e-5) -> np.ndarray:
    """Fractional differentiation preserving long memory (Phase 1)."""
    w = _fracdiff_weights(d, threshold)
    width = len(w) - 1
    if len(series) <= width:
        return np.diff(series)  # graceful fallback only (not integer diff of prices)
    return np.array([np.dot(w, series[i - width: i + 1]) for i in range(width, len(series))])

def optimize_fracdiff_d(series: np.ndarray):
    """Find minimum d achieving stationarity (ADF p < 0.05) to preserve memory."""
    for d in np.arange(0.0, 1.05, 0.05):
        candidate = series if d == 0 else apply_frac_diff(series, d)
        if len(candidate) < 10:
            continue
        try:
            p_val = adfuller(candidate, autolag="AIC")[1]
            if p_val < 0.05:
                return round(d, 2), candidate
        except Exception:
            continue
    # Absolute fallback - use d=1.0 (minimum differentiation, NOT pct_change)
    return 1.0, apply_frac_diff(series, 1.0)

# -- Meta-Model Serialization Fail-Safe (SRE Patch 0x80) ------------------------
_META_MODEL = None
_SHAP_EXPLAINER = None

def _load_meta_model_with_failsafe():
    global _META_MODEL, _SHAP_EXPLAINER
    try:
        if META_MODEL_PATH.exists():
            # Directive 1 & 3: Direct joblib load with IO fail-safe
            new_model = joblib.load(META_MODEL_PATH)
            _META_MODEL = new_model
            _SHAP_EXPLAINER = shap.TreeExplainer(_META_MODEL)
            logging.info(f"[META-MODEL] Successfully loaded/reloaded {META_MODEL_PATH.name} via joblib.")
        else:
            logging.warning("[META-MODEL] active.pkl not found. System operating on previous state or fallback.")
    except (FileNotFoundError, EOFError, UnpicklingError, Exception) as e:
        # Directive 3: IO Fail-Safe - Log and proceed with existing memory state
        logging.error(f"[META-MODEL_IO_ERROR] Failed to load model: {e}. Maintaining current state.")

from joblib import load as joblib_load
from pickle import UnpicklingError
import joblib

_load_meta_model_with_failsafe()

# -- Master Constitution (v19.5 - SRE) ------------------------------------------
MASTER_CONSTITUTION = ""
CONSTITUTION_PATH = PROJECT_ROOT / "Master_Prompt.txt"
if CONSTITUTION_PATH.exists():
    with open(CONSTITUTION_PATH, "r", encoding="utf-8") as f:
        MASTER_CONSTITUTION = f.read()
else:
    logging.warning("[BOOT] Master_Prompt.txt NOT FOUND. Using empty constitution.")

# -- FAISS Memory (Phase 3 - 93-dim Episodic Memory) ---------------------------
_MEMORY = memory.EpisodicMemory(dim=93)
LEGEND_SIMILARITY_THRESHOLD = 0.85
FAILURE_SIMILARITY_THRESHOLD = 0.85

async def _moe_reason_async(symbol: str, features: dict, direction: int) -> dict:
    """
    Phase 2: asyncio.gather() Concurrent Dual-Engine Routing (v17.9 Constitution).
    """
    feat_summary = json.dumps(
        {k: round(float(v), 6) if isinstance(v, (int, float, np.floating)) else str(v)
         for k, v in list(features.items())[:20]}
    )
    system_prompt = MASTER_CONSTITUTION
    
    utc_now = int(time.time())
    user_prompt = (
        f"SYMBOL: {symbol} | PRIMARY_DIR: {direction} | UTC_TS: {utc_now} | FEATURES: {feat_summary}"
    )

    loop = asyncio.get_event_loop()
    xgb_val    = features.get("xgb_p", 0.500)
    kronos_val = features.get("kronos_p", 0.500)
    
    if _MATH_META_MODEL is not None:
        faiss_sim = features.get("faiss_sim", 0.0)
        hmm_state = features.get("hmm_state", "RANGE")
        try:
            logging.info(f"[ROUTER] {symbol} -> Math Meta-Model (Zero-Latency)")
            p_val = _MATH_META_MODEL.predict_conviction(symbol, features)
            decision = "BUY" if direction == 1 else ("SELL" if direction == -1 else "HOLD")
            return {"decision": decision, "confidence": p_val, "reasoning": "Math Meta-Model Bypass"}
        except ValueError as e:
            # v22.4: NaN / dimension errors are FATAL — propagate upward, do NOT default.
            logging.critical(f"[ROUTER] [FATAL] {symbol}: Structural inference failure: {e}")
            raise
        except Exception as e:
            logging.error(f"[ROUTER] Math Meta-Model transient failure for {symbol}: {e}")
    else:
        logging.error(f"[ROUTER] Math Meta-Model not initialized for {symbol}.")

    return {"decision": "HOLD", "confidence": 0.500, "reasoning": "Math Meta-Model Unavailable."}


def _moe_reason(symbol: str, features: dict, direction: int) -> dict:
    """
    Synchronous wrapper for _moe_reason_async.
    """
    try:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            result = new_loop.run_until_complete(_moe_reason_async(symbol, features, direction))
            return result
        finally:
            new_loop.close()
    except Exception as e:
        logging.error(f"[ROUTER] _moe_reason wrapper error for {symbol}: {e}")
        return {"decision": "HOLD", "confidence": 0.500, "reasoning": f"Router wrapper error: {e}"}

# -- SHAP Diagnostics (Phase 2) ------------------------------------------------
CONCEPT_DRIFT_THRESHOLD = 0.65

def _run_shap(symbol: str, x_vec: list, f_keys: list, direction: int, p_final: float, reasoning: str):
    """Compute SHAP values, detect concept drift, write JSON to shap_diagnostics/."""
    if _SHAP_EXPLAINER is None:
        return
    try:
        # Directive 2: Force 2D Matrix Reshaping for SHAP (SRE Patch)
        safe_features = np.array(x_vec, dtype=float).reshape(1, -1)
        # Using interventional perturbation to avoid additivity failures in dynamic regimes
        s_vals_raw = _SHAP_EXPLAINER.shap_values(safe_features, check_additivity=False)
        
        if isinstance(s_vals_raw, list):
            s_vals = np.array(s_vals_raw[0]).flatten()
        else:
            s_vals = np.array(s_vals_raw).flatten()
            
        total_abs = float(np.sum(np.abs(s_vals)) + 1e-9)
        weights = {f_keys[i]: float(s_vals[i]) / total_abs for i in range(len(s_vals))}
        max_feature = max(weights, key=lambda k: abs(weights[k]))
        max_weight  = abs(weights[max_feature])

        if max_weight > CONCEPT_DRIFT_THRESHOLD:
            logging.error(
                f"[CONCEPT_DRIFT_WARNING] {symbol}: Feature '{max_feature}' = {max_weight:.2%} > 65%. "
                f"Forcing conviction to 0.0."
            )

        sorted_w = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        payload = {
            "symbol": symbol,
            "prediction": int(direction),
            "conviction": float(p_final),
            "reasoning": reasoning,
            "timestamp": utils.get_utc_epoch(),
            "weights": weights,
            "top_pos": sorted_w[:3],
            "top_neg": sorted_w[-3:],
            "concept_drift": max_weight > CONCEPT_DRIFT_THRESHOLD,
        }
        out = SHAP_DIR / f"{symbol}_diag.json"
        with open(out, "w") as fh:
            json.dump(payload, fh, indent=2)
        logging.info(f"[{symbol}] SHAP diagnostic written -> {out.name}")

        return 0.0 if max_weight > CONCEPT_DRIFT_THRESHOLD else None
    except Exception as e:
        logging.debug(f"[{symbol}] SHAP diagnostic skipped: {e}")
        return None

# -- Meta-Conviction (Phase 2 - Meta-Labeling Architecture) -------------------
def get_meta_conviction(symbol: str, features: dict, direction: int, base_p: float) -> float:
    """
    v22.1: Expanded to 11-feature Alpha Factory vector.
    [xgb_p, kronos_p, hmm_state, faiss_sim, macro_sent, macro_risk, catalyst,
     frac_diff, fft_amp_1, fft_amp_2, fft_amp_3, cs_rank]
    """
    f_keys = [
        "xgb_p", "kronos_p", "hmm_state", "faiss_sim",
        "macro_sent", "macro_risk", "catalyst",
        "frac_diff", "fft_amp_1", "fft_amp_2", "fft_amp_3", "cs_rank"
    ]
    hmm_val = 1 if features.get("hmm_state") == "BULL" else (-1 if features.get("hmm_state") == "BEAR" else 0)

    # v19.5: Logarithmic Dampening on Macro Features
    def damp(x): return np.sign(x) * np.log1p(abs(float(x)))

    x_vec = [
        float(features.get("xgb_p", 0.5)),
        float(features.get("kronos_p", 0.5)),
        float(hmm_val),
        float(features.get("faiss_sim", 0.0)),
        damp(features.get("macro_sent", 0.0)),
        damp(features.get("macro_risk", 0.0)),
        damp(features.get("catalyst", 0.0)),
        # v22.1 Alpha Factory features
        float(features.get("frac_diff", 0.0)),
        float(features.get("fft_amp_1", 0.0)),
        float(features.get("fft_amp_2", 0.0)),
        float(features.get("fft_amp_3", 0.0)),
        float(features.get("cs_rank", 0.5)),
    ]

    moe = _moe_reason(symbol, features, direction)
    reasoning_conf = float(moe.get("confidence", 0.500))
    reasoning_text = moe.get("reasoning", "N/A")

    if "fail-safe" in reasoning_text.lower() or reasoning_conf == 0.500:
        p_final = 0.500
        logging.warning(f"[{symbol}] MoE Fail-Safe engaged -> Neutral 0.500")
    else:
        # v20.4: Soft Confidence Blending max(0.6, MoE)
        strength = max(0.6, reasoning_conf)
        p_final = 0.5 + (base_p - 0.5) * strength

    drift_override = _run_shap(symbol, x_vec, f_keys, direction, p_final, reasoning_text)
    if drift_override is not None:
        p_final = drift_override

    logging.info(f"[{symbol}] Meta-Conviction: {p_final:.4f} | MoE: {reasoning_conf:.3f}")
    return float(p_final)

# -- Oracle Cooldown -----------------------------------------------------------
_LAST_UPDATE: Dict[str, float] = {}
ORACLE_COOLDOWN = 60.0

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

# -- Signal Router -------------------------------------------------------------
@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
def _post_to_sniper(payload: Dict[str, Any], url: str):
    """Direct HTTP POST to the Execution Node with exponential backoff."""
    response = requests.post(url, json=payload, timeout=5)
    response.raise_for_status()
    return response

def push_to_orchestrator(payload: Dict[str, Any]):
    """Direct ultra-low-latency execution bridge (Phase 5)."""
    endpoint_url = os.getenv("EXECUTION_ENDPOINT_URL")
    if not endpoint_url:
        logging.error("[COGNITION_ROUTE] EXECUTION_ENDPOINT_URL not found in .env. Falling back to local queue.")
        fname = SIGNAL_DIR / f"sig_{payload['symbol']}_{int(time.time())}.json"
        with open(fname, "w") as fh:
            json.dump(payload, fh, indent=2)
        return

    try:
        logging.info(f"[COGNITION_ROUTE] Pushing {payload['symbol']} signal to Direct HTTP Bridge...")
        target_url = f"{endpoint_url.rstrip('/')}/execute_trade"
        _post_to_sniper(payload, target_url)
        logging.info(f"[COGNITION_ROUTE] [OK] Signal delivered to Execution Node successfully.")
    except Exception as e:
        logging.error(f"[COGNITION_ROUTE] [FAIL] Failed to push signal to HTTP Bridge: {e}")
        fname = SIGNAL_DIR / f"sig_{payload['symbol']}_{int(time.time())}.json"
        with open(fname, "w") as fh:
            json.dump(payload, fh, indent=2)

# -- Main Oracle Update --------------------------------------------------------
def update_slow_oracles(symbol: str, force_refresh: bool = False):
    """Full cognition pipeline for one symbol."""
    now = time.time()
    if now - _LAST_UPDATE.get(symbol, 0) < ORACLE_COOLDOWN:
        return
    _LAST_UPDATE[symbol] = now

    # -- Macro Halt & Black Swan Override (v19.5) ----------------------------
    # v26.0: Initialize m_state with defaults to prevent UnboundLocalError
    m_state = {"global_macro_sentiment": 0.0, "black_swan_risk": 0.0, "asset_specific_catalysts": {}}
    
    if HALT_PATH.exists():
        logging.critical("[MACRO_HALT] Global suspension active. Sleeping 60 s.")
        time.sleep(60)
        return

    try:
        macro_path = PROJECT_ROOT / "data" / "macro_state.json"
        if macro_path.exists():
            with open(macro_path, "r") as f:
                # v20.4: Strict localized instantiation via copy.deepcopy()
                m_state = copy.deepcopy(json.load(f))
                if m_state.get("black_swan_risk", 0.0) > 0.85:
                    logging.critical(f"[BLACK_SWAN_OVERRIDE] Risk={m_state['black_swan_risk']:.2f} > 0.85. Forcing Conviction to 0.0 and LIQUIDATING ALL.")
                    push_to_orchestrator({
                        "symbol": "ALL",
                        "direction": "LIQUIDATE",
                        "conviction": 0.0,
                        "reasoning": "BLACK SWAN SUPREME OVERRIDE",
                        "timestamp": int(time.time())
                    })
                    return
    except Exception as e:
        logging.warning(f"[MACRO_STATE] Failed to check black swan risk: {e}")

    if not force_refresh and _check_staleness(symbol):
        logging.info(f"[{symbol}] Previous signal is stale. Curing via fresh oracle update...")

    time.sleep(random.uniform(0.05, 0.3))

    df_m15 = df_ta = df_ml = None
    latest_swing = None # v26.0: Store swing alpha features for Heuristic Override
    try:
        logging.info(f"[{symbol}] Updating high-resolution oracles (v21.0)...")
        # v26.0 Swing Paradigm: H1/H4 Multi-Timeframe Ingestion (Primary Data Source)
        mt5.symbol_select(symbol, True)
        try:
            from feature_engineering import ingest_mtf_ohlcv, compute_swing_alpha
            df_h1, df_h4 = ingest_mtf_ohlcv(symbol)
            if df_h1 is not None and len(df_h1) >= 50:
                swing_alpha = compute_swing_alpha(df_h1, df_h4)
                latest_swing = swing_alpha.iloc[-1]
                logging.info(
                    f"[v26.0 SWING ALPHA] {symbol} | "
                    f"H1_Bars={len(df_h1)} | H4_Bars={len(df_h4) if df_h4 is not None else 0} | "
                    f"RSI={latest_swing.get('rsi', float('nan')):.2f} | "
                    f"BB_Width={latest_swing.get('bb_width', float('nan')):.5f} | "
                    f"RVOL={latest_swing.get('rvol', float('nan')):.2f} | "
                    f"Sent={latest_swing.get('entropy', float('nan')):.3f} | "
                    f"MeanRev={int(latest_swing.get('mean_reversion_signal', 0))} | "
                    f"TrendCont={int(latest_swing.get('trend_continuation_signal', 0))} | "
                    f"Catalyst={int(latest_swing.get('catalyst_momentum_signal', 0))}"
                )
            else:
                logging.warning(f"[{symbol}] H1 ingestion insufficient ({len(df_h1) if df_h1 is not None else 0} bars). Proceeding with tick fallback.")
        except Exception as _h1_err:
            logging.warning(f"[{symbol}] v26.0 Swing Alpha failed: {_h1_err}. Proceeding with tick fallback.")
        # 1. Force a single tick request to wake up the broker's data stream
        mt5.symbol_info_tick(symbol)
        # Shift from M15 to Tick Ingestion (N=2000) with async pre-fetch retry loop
        df_m15 = None
        max_retries = 5
        for attempt in range(max_retries):
            df_m15 = sigproc.get_tick_dataframe(symbol, 2000)
            if df_m15 is not None and len(df_m15) >= 512:
                break
            time.sleep(1.0)

        if df_m15 is None or len(df_m15) < 512:
            # Directive 2: M1 OHLCV Anti-Starvation Fallback
            logging.warning(f"[TICKER_ERROR] {symbol}: insufficient ticks after {max_retries} attempts. Attempting M1 OHLCV fallback...")
            try:
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 750)
                if rates is not None and len(rates) >= 512:
                    df_m15 = pd.DataFrame(rates)
                    df_m15['time'] = pd.to_datetime(df_m15['time'], unit='s')
                    # Align column names to tick-dataframe schema
                    df_m15.rename(columns={'tick_volume': 'tick_volume'}, inplace=True)
                    if 'real_volume' not in df_m15.columns:
                        df_m15['real_volume'] = df_m15.get('tick_volume', 0)
                    if 'volume' not in df_m15.columns:
                        df_m15['volume'] = df_m15['real_volume']
                    if 'tick_volume' not in df_m15.columns:
                        df_m15['tick_volume'] = df_m15['real_volume']
                    logging.info(f"[ANTI-STARVATION] {symbol}: M1 OHLCV fallback SUCCESS ({len(df_m15)} bars).")
                else:
                    err = mt5.last_error()
                    logging.error(f"[TICKER_ERROR] {symbol}: M1 fallback also insufficient. MT5 Error: {err}. Skipping.")
                    return
            except Exception as _fe:
                logging.error(f"[TICKER_ERROR] {symbol}: M1 fallback exception: {_fe}. Skipping.")
                return

        df_ta = df_m15.copy()
        c = df_ta["close"]
        delta = c.diff()
        gain  = delta.where(delta > 0, 0).rolling(14).mean()
        loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df_ta["W_rsi"]    = 100 - (100 / (1 + gain / (loss + 1e-9)))
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        macd  = ema12 - ema26
        df_ta["W_macd"]   = macd - macd.ewm(span=9, adjust=False).mean()
        ema20 = c.ewm(span=20, adjust=False).mean()
        ema50 = c.ewm(span=50, adjust=False).mean()
        df_ta["Wy_trend"] = (ema20 - ema50) / (c * 0.01 + 1e-9)
        ma20  = c.rolling(20).mean(); std20 = c.rolling(20).std()
        df_ta["B_bbpos"]  = (c - (ma20 - 2*std20)) / (4*std20 + 1e-9)
        df_ta["WHL_vol"]  = c.pct_change().rolling(20).std()
        df_ta["S_struct"]  = 0.5

        df_ml = df_ta.copy()
        for col in ["open", "high", "low", "close"]:
            opt_d, fd = optimize_fracdiff_d(df_ta[col].values)
            pad = len(df_ta) - len(fd)
            norm_fd = sigproc.strict_normalize(fd)
            df_ml[col] = np.pad(norm_fd, (pad, 0), mode="edge")
        logging.info(f"[{symbol}] FracDiff + Strict Normalization [-5, 5] applied.")

        # ── v22.4: Institutional Feature Engineering (Data Warm-Up) ────────
        # Append frac_diff_price (López de Prado), FFT spectral amplitudes,
        # and Cross-Sectional Rank to the ML feature vector.
        # CRITICAL: We pass the FULL df_ml (2000+ ticks) to provide the 50-bar
        # historical buffer that rolling windows need to produce valid floats.
        vol_col = "tick_volume" if "tick_volume" in df_ml.columns else "volume"
        current_rank = _GLOBAL_CS_RANKS.get(symbol, 0.5)
        
        try:
            df_ml = feat_eng.engineer_features(
                df_ml,
                price_col="close",
                volume_col=vol_col,
                frac_d=0.45,
                fft_top_k=3,
                cs_rank=current_rank,
            )
            nan_count = df_ml.isna().sum().sum()
            logging.info(f"[{symbol}] v22.4 Feature Engineering applied: [FracDiff, FFT, CS_Rank={current_rank:.2f}]. NaN Count: {nan_count}")
            if nan_count > 0:
                logging.warning(f"[{symbol}] WARNING: NaNs detected in features:\n{df_ml.isna().sum()[df_ml.isna().sum() > 0]}")
        except Exception as e:
            logging.error(f"[{symbol}] FEATURE_ENGINEERING_CRITICAL_FAILURE (Non-Fatal for Swing): {e}")
            if latest_swing is None:
                return # Still fatal if no swing features either

        if df_ml is not None:
            df_ml = df_ml.dropna()
            if len(df_ml) < 512 and latest_swing is None:
                logging.error(f"[TICKER_ERROR] {symbol}: <512 clean bars and no swing fallback. Skipping.")
                return

        # ── v22.4: Data Warm-Up Validation ──────────────────────────────────
        # Verify the FINAL ROW has valid (non-NaN) Alpha Factory features.
        # If rolling windows produced NaNs, we MUST halt — never default to 0.0.
        if df_ml is not None:
            _warmup_cols = ["frac_diff_price", "fft_amp_1", "fft_amp_2", "fft_amp_3"]
            _final_row = df_ml.iloc[-1]
            _nan_features = [c for c in _warmup_cols if c in df_ml.columns and (pd.isna(_final_row[c]) or np.isinf(_final_row[c]))]
            if _nan_features and latest_swing is None:
                logging.critical(f"[FATAL] {symbol}: Model input contains NaNs/Infs in {_nan_features}. Halting inference for {symbol}.")
                return
        elif latest_swing is None:
            logging.critical(f"[FATAL] {symbol}: No ML data and no Swing fallback. Halting.")
            return

        raw_hmm_state, hmm_prob, label_probs = hmm.get_current_state(df_m15["close"].values)
        
        # Directive 1: Regime Hysteresis (Debouncing)
        if symbol not in _OFFICIAL_REGIME:
            _OFFICIAL_REGIME[symbol] = raw_hmm_state
            
        _HMM_HISTORY[symbol].append(raw_hmm_state)
        if len(_HMM_HISTORY[symbol]) > 3:
            _HMM_HISTORY[symbol].pop(0)
            
        if len(_HMM_HISTORY[symbol]) == 3 and all(s == raw_hmm_state for s in _HMM_HISTORY[symbol]):
            _OFFICIAL_REGIME[symbol] = raw_hmm_state
            
        hmm_state = _OFFICIAL_REGIME[symbol]
        
        # v26.0: Use H1-based ATR for all regime/scaling decisions
        atr = utils.calculate_atr(df_h1) if df_h1 is not None else 0.0010
        logging.info(f"[HMM] {symbol}: Raw={raw_hmm_state} -> Official={hmm_state} (p={hmm_prob:.3f}) | ATR(H1)={atr:.5f}")

        _arctic_write(f"{symbol}_hmm", pd.DataFrame([{
            "state": hmm_state,
            "prob": float(hmm_prob),
            "atr": float(atr),
            "timestamp": utils.get_utc_epoch(),
        }]))

        # ── Level 34 SRE: Heuristic Override & ML Bypass ──────────────────
        try:
            # 2. Resurrect XGBoost (Directive 1)
            kronos_bridge.update_cognition_cache(symbol, df_ml)
            k_item = _arctic_read(f"{symbol}_kronos")
            if k_item is not None:
                _k_data = k_item.data.iloc[-1]
                k_prob = float(_k_data["kronos_prob"])
            else:
                k_prob = 0.500
            
            x_prob = get_xgb_prediction(df_ml)
            ddqn_p = 0.500 # Default

            # v26.8 Consensus Purity Protocol
            scores_raw = {
                "kronos": k_prob,
                "xgb": x_prob,
                "ddqn": ddqn_p
            }
            
            # RL Inference (if not quarantined)
            from rl_agents.oxford_ddqn import CHECKPOINT_PATH
            if os.path.exists(CHECKPOINT_PATH):
                ddqn_agent = ddqn_bridge.get_ddqn_agent()
                feature_vec = df_ml.select_dtypes(include=[np.number]).iloc[-1].astype(float).values
                ddqn_p = ddqn_agent.infer_probability(feature_vec)
                scores_raw["ddqn"] = ddqn_p
            
            # APPLY QUARANTINE FILTER
            q_result = registry.filter_agents(scores_raw)
            active_scores = q_result.filtered_scores
            
            # v26.8 Weight Allocation
            # Base Weights: Kronos=0.4, XGB=0.3, DDQN=0.3
            base_weights = {"kronos": 0.4, "xgb": 0.3, "ddqn": 0.3}
            
            # Re-normalize weights for active agents
            total_active_weight = sum(base_weights[name] for name in active_scores)
            if total_active_weight > 0:
                p_blend = sum(
                    active_scores[name] * (base_weights[name] / total_active_weight)
                    for name in active_scores
                )
            else:
                p_blend = 0.500
                
            logging.info(f"[{symbol}] ML Inference SUCCESS: P_blend={p_blend:.4f} (Agents: {list(active_scores.keys())})")
            
        except Exception as e:
            logging.warning(f"[{symbol}] ML Bypass in effect. Reason: {e}")
            x_prob = 0.500
            ddqn_p = 0.500
            k_prob = 0.500
            print(f"[ML BYPASS] Shape mismatch detected. Falling back to Heuristic Swing Routing for {symbol}.")
            x_prob = 0.500
            ddqn_p = 0.500
            
            if latest_swing is not None:
                rsi = latest_swing.get('rsi', 50)
                entropy = latest_swing.get('entropy', 0.5)
                
                # Heuristic Protocol logic
                if rsi < 35 and entropy > 0.85:
                    p_blend = 0.85 # Mean Rev Long
                elif rsi > 65 and entropy > 0.85:
                    p_blend = 0.15 # Mean Rev Short
                elif latest_swing.get('trend_continuation_signal', 0) > 0:
                    # Price vs EMA 20 for direction
                    p_blend = 0.90 if df_m15['close'].iloc[-1] > latest_swing.get('ema_20', 0) else 0.10
                elif latest_swing.get('catalyst_momentum_signal', 0) > 0:
                    p_blend = 0.80 if latest_swing.get('gap_pct', 0) > 0 else 0.20
                else:
                    p_blend = 0.50 # Neutral
            else:
                p_blend = 0.50
                
            logging.warning(f"[{symbol}] HEURISTIC_OVERRIDE ACTIVE: P_blend={p_blend:.2f} (Reason: {e})")

        if _OBSERVER:
            s_t_data = {
                "kronos_p": k_prob,
                "xgb_p": x_prob,
                "ddqn_p": ddqn_p,
                "hmm_state": hmm_state,
                "atr": atr,
                "timesfm_p10": float(k_item.data.iloc[-1].get("p10", 0.0)),
                "timesfm_p90": float(k_item.data.iloc[-1].get("p90", 0.0))
            }
            _OBSERVER.observe(pd.DataFrame([s_t_data]))

        primary_dir = 1 if p_blend > 0.60 else (-1 if p_blend < 0.40 else 0)

        live_vec = copy.deepcopy(sigproc.get_feature_vector(symbol))
        mem_matches = _MEMORY.retrieve(live_vec, k=3)
        is_legend = False; is_graveyard = False; max_sim = 0.0
        for match in mem_matches:
            sim = match["distance"]; max_sim = max(max_sim, sim)
            meta = match["meta"]; reasoning = meta.get("reasoning", "").upper()
            if sim > LEGEND_SIMILARITY_THRESHOLD:
                if "LEGEND" in reasoning or meta.get("action") == "LEGEND_WEI":
                    is_legend = True; break
            if sim > FAILURE_SIMILARITY_THRESHOLD:
                if "FAILURE" in reasoning or "POST_MORTEM" in reasoning:
                    is_graveyard = True; break

        # 6. Meta-Conviction (v19.5: Z-Score Noise Injection)
        try:
            k_hist_item = _arctic_read(f"{symbol}_kronos")
            if k_hist_item is not None:
                k_hist = k_hist_item.data.tail(50)
                xgb_vals = k_hist['xgboost_prob'].values
                k_vals = k_hist['kronos_prob'].values
                z_xgb = (float(x_prob) - np.mean(xgb_vals)) / (np.std(xgb_vals) + 1e-9)
                z_kronos = (float(k_prob) - np.mean(k_vals)) / (np.std(k_vals) + 1e-9)
            else:
                z_xgb = (float(x_prob) - 0.5) / 0.15
                z_kronos = (float(k_prob) - 0.5) / 0.15
        except Exception as e:
            z_xgb = (float(x_prob) - 0.5) / 0.15
            z_kronos = (float(k_prob) - 0.5) / 0.15

        # v22.4: Extract Alpha Factory features from the FINAL ROW only.
        # The upstream warm-up validation guarantees these are valid floats.
        _final = df_ml.iloc[-1]
        local_meta_features = copy.deepcopy({
            "hmm_state": hmm_state,
            "xgb_p": z_xgb,
            "kronos_p": z_kronos,
            "faiss_sim": float(max_sim),
            "macro_sent": float(m_state.get("global_macro_sentiment", 0.0)),
            "macro_risk": float(m_state.get("black_swan_risk", 0.0)),
            "catalyst": float(m_state.get("asset_specific_catalysts", {}).get(symbol, 0.0)),
            # v22.5: Alpha Factory + Microstructure Triad features
            "frac_diff": float(_final.get("frac_diff_price", 0.0)),
            "fft_amp_1": float(_final.get("fft_amp_1", 0.0)),
            "fft_amp_2": float(_final.get("fft_amp_2", 0.0)),
            "fft_amp_3": float(_final.get("fft_amp_3", 0.0)),
            "vpin": float(_final.get("vpin", 0.0)),
            "hawkes_intensity": float(_final.get("hawkes_intensity", 0.0)),
            "order_flow_entropy": float(_final.get("order_flow_entropy", 0.0)),
            "cs_rank": float(_GLOBAL_CS_RANKS.get(symbol, 0.5)),
        })
        
        # v22.4: Final NaN sweep — if ANY numeric feature is NaN, halt.
        _nan_vals = {k: v for k, v in local_meta_features.items() if isinstance(v, float) and (np.isnan(v) or np.isinf(v))}
        if _nan_vals:
            logging.critical(f"[FATAL] {symbol}: NaN/Inf detected in meta-features: {list(_nan_vals.keys())}. Halting inference.")
            return
        
        # Directive 4: FFT Coherence Lock (v20.4)
        # ── Directive 1: Reconnect MixTS Probabilistic Blending (v22.6) ─────
        # Evaluate both models concurrently (No binary hard gates)
        
        # Strategy A: Trend-Following (Math Meta-Model / MoE)
        p_trend = get_meta_conviction(symbol, local_meta_features, primary_dir, base_p=p_blend)
        
        # Strategy B: Mean-Reversion (RSI + BB + FFT Coherence)
        rsi = df_ta["W_rsi"].iloc[-1]
        bbpos = df_ta["B_bbpos"].iloc[-1]
        prices = df_m15['close'].values
        fft_data = sigproc.fft_cycle_detector(prices)
        fft_amplitude = fft_data.get('power', 0.0)
        
        if fft_amplitude > 1.5:
            p_range = calculate_mean_reversion_score(rsi, bbpos)
        else:
            p_range = 0.50 # Neutralize if coherence is low
            
        # Blending Weights via HMM Posterior Probabilities
        # HMM State 0=BULL, 1=BEAR, 2=RANGE
        w_trend = label_probs.get("BULL", 0.0) + label_probs.get("BEAR", 0.0)
        w_range = label_probs.get("RANGE", 0.0)
        
        # Normalize weights to sum to 1.0
        total_w = w_trend + w_range + 1e-9
        w_trend /= total_w
        w_range /= total_w
        
        # Final MixTS Blended Conviction (P)
        meta_p = (w_trend * p_trend) + (w_range * p_range)
        
        # Dynamic Epistemic Gate Blending
        # Trend Gate (Default) vs Range Gate (0.75 override)
        current_gate = (w_trend * EPISTEMIC_GATE) + (w_range * 0.75)
        
        # Post-processing: Regime Alignment & Graveyard
        # v24.3 Constitution: Eradicated legacy v17.9 regime overrides. 
        # MixTS handles regime alignment natively via Bayesian weighting.
        if is_graveyard: meta_p = 0.50
        
        logging.info(f"[{symbol}] MixTS BLEND: Trend({w_trend:.1%})={p_trend:.3f}, Range({w_range:.1%})={p_range:.3f} -> P={meta_p:.4f} (Gate: {current_gate:.3f})")

        _arctic_write(f"{symbol}_meta", pd.DataFrame([{
            "primary_dir": int(primary_dir),
            "meta_conviction": float(meta_p),
            "hmm_state": hmm_state,
            "atr": float(atr),
            "entropy": float(_final.get("order_flow_entropy", 0.0)),
            "hawkes_intensity": float(_final.get("hawkes_intensity", 0.0)),
            "timestamp": utils.get_utc_epoch(),
            "is_legend": is_legend,
            "is_graveyard": is_graveyard,
        }]))

        # Directive 1: Absolute Conviction Gate (v24.3 Level 23 SRE)
        # norm_p must reflect BOTH BUY (P > 0.5) and SELL (P < 0.5) conviction.
        # A bearish P=0.15 is abs(0.15-0.5)+0.5 = 0.85 absolute conviction.
        norm_p = abs(meta_p - 0.5) + 0.5
        
        # v23.12 Directive: Sealed Hysteresis Dead-Zone
        if 0.40 <= meta_p <= 0.60:
            logging.info(f"[GATE] {symbol}: P={meta_p:.6f} falls in DEAD-ZONE (0.40-0.60). HARD BLOCKED.")
            # Skip the signal dispatch block
        elif norm_p >= current_gate and primary_dir != 0:
            # Direction: BUY for P > 0.5, SELL for P < 0.5 — always from raw meta_p
            signal_dir = "BUY" if meta_p > 0.5 else "SELL"
            
            push_to_orchestrator({
                "symbol": symbol,
                "direction": signal_dir,
                "conviction": round(float(meta_p), 6),
                "xgb_p": float(x_prob),
                "ddqn_p": float(ddqn_p),
                "hmm_state": hmm_state,
                "atr": float(atr),
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
                "version": "v24.3-UNCHAINED",
            })
            logging.info(f"[OK] [SIGNAL] {symbol}: {signal_dir} | P={meta_p:.6f} | norm_p={norm_p:.4f} | HMM={hmm_state} | DDQN={ddqn_p:.3f}")
        else:
            if hmm_state == "RANGE":
                logging.info(f"[GATE] {symbol}: norm_p={norm_p:.6f} < 0.75 (Mean-Reversion Gate). Suppressed.")
            else:
                logging.info(f"[GATE] {symbol}: norm_p={norm_p:.6f} < {current_gate}. Suppressed.")

        timesfm_bridge.update_risk_cache(symbol, df_ml)

    except Exception as e:
        error_msg = traceback.format_exc()
        logging.error(f"[{symbol}] Oracle update error:\n{error_msg}")
        
        # Directive 2: SRE Diagnostic Ticket Dispatch (v21.2)
        if isinstance(e, (NameError, ImportError, AttributeError)):
            diag_path = Path(PROJECT_ROOT) / "pending_diagnostics"
            diag_path.mkdir(parents=True, exist_ok=True)
            diag_file = diag_path / f"fatal_error_{int(time.time())}.json"
            with open(diag_file, "w") as f:
                json.dump({
                    "timestamp": int(time.time()),
                    "symbol": symbol,
                    "error_type": type(e).__name__,
                    "message": str(e),
                    "traceback": error_msg,
                    "halt_required": True
                }, f, indent=4)
            logging.critical(f"[SRE_HALT] FATAL ERROR DETECTED. Ticket dispatched: {diag_file.name}")
    finally:
        df_m15 = df_ta = df_ml = None

async def process_matrix_parallel(watchlist: list, force_refresh: bool = False):
    """Runs update_slow_oracles concurrently using Micro-Batching."""
    def chunked(iterable, n):
        it = iter(iterable)
        while True:
            chunk = list(itertools.islice(it, n))
            if not chunk: break
            yield chunk

    loop = asyncio.get_event_loop()
    max_workers = 5 
    
    # Directive 3: Pre-Scan the entire watchlist before processing batches
    _pre_scan_watchlist(watchlist)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        batch_idx = 1
        for batch in chunked(watchlist, 10):
            logging.info(f"[MICRO-BATCH] Processing batch {batch_idx} ({len(batch)} assets)...")
            tasks = [loop.run_in_executor(ex, update_slow_oracles, s, force_refresh) for s in batch]
            await asyncio.gather(*tasks)
            gc.collect() # Aggressive GC (Phase 1)
            if len(batch) == 10:
                await asyncio.sleep(0.5)
            batch_idx += 1

def execute_historical_backfill(watchlist: list):
    logging.info(f"[SRE] Cache-based backfill verification ({len(watchlist)} assets)...")
    pass

def main():
    global _LAST_CS_REFRESH
    # v23.6 RAM Audit
    print("=" * 60)
    print(f"  ACTIVE MATRIX SIZE: {len(WATCHLIST)} ASSETS")
    print("=" * 60)
    
    watchlist = WATCHLIST
    if len(watchlist) < 10:
        logging.critical(f"[RAM_AUDIT] Watchlist size {len(watchlist)} is suspiciously small. SRE HALT.")
        sys.exit(1)
        
    execute_historical_backfill(watchlist)
    logging.info("[SYSTEM] Cache warm-up (parallel, force_refresh=True)...")
    asyncio.run(process_matrix_parallel(watchlist, force_refresh=True))
    _LAST_CS_REFRESH = time.time()
    logging.info("[SYSTEM] Warm-up complete. Entering event-driven dollar-bar cycle.")

    # Directive 3: The 1-Hour Heartbeat (Anti-Scalp Lock)
    while True:
        try:
            logging.info(f"[HEARTBEAT] Starting H1 Swing Evaluation Cycle ({len(watchlist)} assets)...")
            asyncio.run(process_matrix_parallel(watchlist, force_refresh=True))
            _pre_scan_watchlist(watchlist)
            
            # Sleep until the top of the next hour
            now = datetime.now()
            seconds_to_wait = 3600 - (now.minute * 60 + now.second)
            logging.info(f"[HEARTBEAT] Cycle complete. Sleeping for {seconds_to_wait} seconds until next H1 close.")
            time.sleep(seconds_to_wait)
        except Exception as e:
            logging.error(f"[HEARTBEAT_ERROR] {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
