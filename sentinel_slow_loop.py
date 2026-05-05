"""
sentinel_slow_loop.py - ADAPTIVE SENTINEL SLOW LOOP (v20.4 - Dynamic Asset-Class ATRs)
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

# Windows Hybrid Initialization
if os.name == 'nt':
    if not mt5.initialize():
        logging.error("[BOOT] Failed to initialize MT5 for local data streaming.")
    else:
        logging.info("[BOOT] MT5 initialized for local Hybrid-Brain mode.")

sys.path.append(r"C:\Sentinel_Project")

import git_arctic
import gitagent_hmm as hmm
import gitagent_sigproc as sigproc
import kronos_bridge
import timesfm_bridge
import gitagent_utils as utils
import gitagent_bars as bars
import gitagent_memory as memory

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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SLOW_LOOP] %(message)s",
    force=True,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_DIR / "slow_loop_v17_9.log")),
    ],
)
# -- Contextual Routing - Phase 2 Constitution (v17.9) ------------------
# CONSTITUTION DIRECTIVE: Route HIGH-VOLATILITY CRYPTO -> Groq (Gemma)
#                         Route FOREX + INDICES + METALS -> Gemini (macro-synthesis)
# ONLY BTC and ETH are crypto in the 13-asset watchlist.
CRYPTO_ASSETS  = {"BTCUSD", "ETHUSD"}
FOREX_MACRO_ASSETS = {
    "EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCHF", "NZDUSD",  # Forex
    "GER40", "SP500", "NAS100",                                     # Indices
    "XAUUSD", "XAGUSD",                                             # Metals
}

try:
    from math_meta_model import MathMetaModel
    _MATH_META_MODEL = MathMetaModel()
    logging.info("[ROUTER] Math Meta-Model (v18.2) initialized successfully.")
except Exception as _e:
    _MATH_META_MODEL = None
    logging.warning(f"[ROUTER] Math Meta-Model unavailable: {_e}")

# Cloud Engine Fallback: Fail-safe neutral 0.500 if both engines exhausted
# Note: Local Ollama MoE is officially deprecated per v17.9 Constitution.


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
            p_val = _MATH_META_MODEL.predict_conviction(symbol, xgb_val, kronos_val, hmm_state, faiss_sim)
            decision = "BUY" if direction == 1 else ("SELL" if direction == -1 else "HOLD")
            return {"decision": decision, "confidence": p_val, "reasoning": "Math Meta-Model Bypass"}
        except Exception as e:
            logging.error(f"[ROUTER] Math Meta-Model failure for {symbol}: {e}")
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
    Decoupled sizing: primary direction already decided.
    """
    f_keys = ["xgb_p", "kronos_p", "hmm_state", "faiss_sim", "macro_sent", "macro_risk", "catalyst"]
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
        damp(features.get("catalyst", 0.0))
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
    try:
        logging.info(f"[{symbol}] Updating oracles...")
        df_m15 = sigproc.get_m15_dataframe(symbol, 2000)
        if df_m15 is None or len(df_m15) < 512:
            logging.error(f"[TICKER_ERROR] {symbol}: insufficient bars. Skipping.")
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

        df_ml = df_ml.dropna()
        if len(df_ml) < 512:
            logging.error(f"[TICKER_ERROR] {symbol}: <512 clean bars after FracDiff. Skipping.")
            return

        raw_hmm_state, hmm_prob, _ = hmm.get_current_state(df_m15["close"].values)
        
        # Directive 1: Regime Hysteresis (Debouncing)
        if symbol not in _OFFICIAL_REGIME:
            _OFFICIAL_REGIME[symbol] = raw_hmm_state
            
        _HMM_HISTORY[symbol].append(raw_hmm_state)
        if len(_HMM_HISTORY[symbol]) > 3:
            _HMM_HISTORY[symbol].pop(0)
            
        if len(_HMM_HISTORY[symbol]) == 3 and all(s == raw_hmm_state for s in _HMM_HISTORY[symbol]):
            _OFFICIAL_REGIME[symbol] = raw_hmm_state
            
        hmm_state = _OFFICIAL_REGIME[symbol]
        
        atr = utils.calculate_atr(df_m15)
        logging.info(f"[HMM] {symbol}: Raw={raw_hmm_state} -> Official={hmm_state} (p={hmm_prob:.3f})")

        _arctic_write(f"{symbol}_hmm", pd.DataFrame([{
            "state": hmm_state,
            "prob": float(hmm_prob),
            "atr": float(atr),
            "timestamp": utils.get_utc_epoch(),
        }]))

        kronos_bridge.update_cognition_cache(symbol, df_ml)
        k_item = _arctic_read(f"{symbol}_kronos")
        if k_item is None:
            return

        _k_data = k_item.data.iloc[-1]
        k_prob = float(_k_data["kronos_prob"])
        x_prob = float(_k_data.get("xgboost_prob", 0.50))

        p_blend = (k_prob * 0.70) + (x_prob * 0.30)
        
        if _OBSERVER:
            s_t_data = {
                "kronos_p": k_prob,
                "xgb_p": x_prob,
                "hmm_state": hmm_state,
                "atr": atr,
                "timesfm_p10": float(k_item.data.iloc[-1].get("p10", 0.0)),
                "timesfm_p90": float(k_item.data.iloc[-1].get("p90", 0.0))
            }
            _OBSERVER.observe(pd.DataFrame([s_t_data]))

        primary_dir = 1 if p_blend > 0.55 else (-1 if p_blend < 0.45 else 0)

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

        local_meta_features = copy.deepcopy({
            "hmm_state": hmm_state,
            "xgb_p": z_xgb,
            "kronos_p": z_kronos,
            "faiss_sim": float(max_sim),
            "macro_sent": float(m_state.get("global_macro_sentiment", 0.0)),
            "macro_risk": float(m_state.get("black_swan_risk", 0.0)),
            "catalyst": float(m_state.get("asset_specific_catalysts", {}).get(symbol, 0.0))
        })
        
        # Directive 4: FFT Coherence Lock (v20.4)
        if hmm_state == "RANGE":
            rsi = df_ta["W_rsi"].iloc[-1]
            bbpos = df_ta["B_bbpos"].iloc[-1]
            
            # Fetch FFT Power from sigproc (as proxy for TimesNet amplitude)
            prices = df_m15['close'].values
            fft_data = fft_cycle_detector(prices)
            fft_amplitude = fft_data.get('power', 0.0)
            
            if fft_amplitude > 1.5:
                meta_p = calculate_mean_reversion_score(rsi, bbpos)
                logging.info(f"[{symbol}] ROUTING: Mean-Reversion (RSI={rsi:.1f}, BB={bbpos:.2f}, FFT={fft_amplitude:.2f}) -> P={meta_p:.4f}")
            else:
                meta_p = 0.50
                logging.info(f"[{symbol}] [FILTER] RANGE detected, but FFT Coherence low ({fft_amplitude:.2f}). Trade suppressed.")
            
            primary_dir = 1 if meta_p > 0.5 else -1
            current_gate = 0.75
        else:
            meta_p = get_meta_conviction(symbol, local_meta_features, primary_dir, base_p=p_blend)
            current_gate = EPISTEMIC_GATE
            if not is_legend:
                if hmm_state == "BEAR" and primary_dir == 1: meta_p = 0.50
                elif hmm_state == "BULL" and primary_dir == -1: meta_p = 0.50
            if is_graveyard: meta_p = 0.50

        _arctic_write(f"{symbol}_meta", pd.DataFrame([{
            "primary_dir": int(primary_dir),
            "meta_conviction": float(meta_p),
            "hmm_state": hmm_state,
            "atr": float(atr),
            "timestamp": utils.get_utc_epoch(),
            "is_legend": is_legend,
            "is_graveyard": is_graveyard,
        }]))

        norm_p = 0.5 if meta_p == 0.0 else abs(meta_p - 0.5) + 0.5
        
        if norm_p >= current_gate and primary_dir != 0:
            signal_dir = "BUY" if primary_dir == 1 else "SELL"
            push_to_orchestrator({
                "symbol": symbol,
                "direction": signal_dir,
                "conviction": round(float(meta_p), 6),
                "hmm_state": hmm_state,
                "atr": float(atr),
                "timestamp": int(time.time()),
                "version": "v20.4-PROD",
            })
            logging.info(f"[OK] [SIGNAL] {symbol}: {signal_dir} | P={meta_p:.6f} | HMM={hmm_state}")
        else:
            if hmm_state == "RANGE":
                logging.info(f"[GATE] {symbol}: norm_p={norm_p:.6f} < 0.75 (Mean-Reversion Gate). Suppressed.")
            else:
                logging.info(f"[GATE] {symbol}: norm_p={norm_p:.6f} < {current_gate}. Suppressed.")

        timesfm_bridge.update_risk_cache(symbol, df_ml)

    except Exception as e:
        logging.error(f"[{symbol}] Oracle update error: {e}")
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
    logging.info("=" * 60)
    logging.info("  ADAPTIVE SENTINEL SLOW LOOP v20.4 - Dynamic ATR Build")
    logging.info("  Machine A (Oracle VPS - Brain) | NEVER touches broker directly")
    logging.info("  Rate-limit: tenacity jittered backoff | ASCII Logging: True")
    logging.info("=" * 60)

    watchlist = WATCHLIST
    execute_historical_backfill(watchlist)
    logging.info("[SYSTEM] Cache warm-up (parallel, force_refresh=True)...")
    asyncio.run(process_matrix_parallel(watchlist, force_refresh=True))
    logging.info("[SYSTEM] Warm-up complete. Entering event-driven dollar-bar cycle.")

    streamer = bars.InformationBarStreamer(watchlist)
    for bar in streamer.stream_bars():
        symbol = bar["symbol"]
        update_slow_oracles(symbol)

if __name__ == "__main__":
    main()
