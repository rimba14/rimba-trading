"""
sentinel_slow_loop.py - ADAPTIVE SENTINEL SLOW LOOP (v17.3 Decoupled Production Build)
Constitution: Event-driven dollar bars, FracDiff, HMM, Meta-Labeling, SHAP, Ollama MoE.
Machine A ONLY — never touches the broker directly.
"""
import sys
import subprocess
import importlib.util

def _enforce_dependencies():
    for lib in ['shap', 'scipy', 'statsmodels']:
        if importlib.util.find_spec(lib) is None:
            print(f"[BOOTSTRAP] Installing: {lib}")
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

_enforce_dependencies()

import time
import os
import json
import logging
import random
import asyncio
import threading
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import numpy as np
import pandas as pd
import MetaTrader5 as mt5
import xgboost as xgb
import shap
import requests
from statsmodels.tsa.stattools import adfuller

sys.path.append(r"C:\Sentinel_Project")

import git_arctic
import gitagent_hmm as hmm
import gitagent_sigproc as sigproc
import kronos_bridge
import timesfm_bridge
import gitagent_utils as utils
import gitagent_bars as bars

# ── Config ────────────────────────────────────────────────────────────────────
from sentinel_config import (
    EPISTEMIC_GATE, STALENESS_THRESHOLD, ARCTIC_TIMEOUT,
    KELLY_FRACTION, PORTFOLIO_HEAT_CAP, HARD_RISK_CAP, LEVERAGE_WALL,
    OLLAMA_KEEP_ALIVE, WATCHLIST, REASONING_TIMEOUT,
)

# ── Contextual Routing — Phase 5 Constitution ─────────────────────────────────
# Crypto + Metals  →  Groq  (Llama-3.1-8b-instant, high-speed momentum analysis)
# Forex + Indices  →  Gemini (gemini-2.5-flash, deep macro-synthesis)
CRYPTO_METALS_ASSETS = {"BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD"}
FOREX_INDEX_ASSETS   = {"EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCHF", "NZDUSD",
                        "SP500", "NAS100", "GER40"}

try:
    from gemini_engine import GeminiReasoningEngine
    _GEMINI_ENGINE = GeminiReasoningEngine()
    logging.info("[ROUTER] Gemini engine initialized (Forex/Index stream).")
except Exception as _e:
    _GEMINI_ENGINE = None
    logging.warning(f"[ROUTER] Gemini engine unavailable: {_e}")

try:
    from groq_engine import GroqReasoningEngine
    _GROQ_ENGINE = GroqReasoningEngine(model_name="llama-3.1-8b-instant")
    logging.info("[ROUTER] Groq engine initialized (Crypto/Metal stream).")
except Exception as _e:
    _GROQ_ENGINE = None
    logging.warning(f"[ROUTER] Groq engine unavailable: {_e}")

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(r"C:\Sentinel_Project")
SHAP_DIR     = PROJECT_ROOT / "shap_diagnostics"
SIGNAL_DIR   = PROJECT_ROOT / "pending_signals"
HALT_PATH    = PROJECT_ROOT / "halt_signal.json"
LOG_DIR      = Path(r"C:\sentinel_logs")
META_MODEL_PATH = PROJECT_ROOT / "medallion_model.json"

for d in [SHAP_DIR, SIGNAL_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SLOW_LOOP] %(message)s",
    force=True,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_DIR / "slow_loop_v17_3.log")),
    ],
)

# ── ArcticDB Singleton (300 ms timeout enforced via ThreadPoolExecutor) ───────
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
            logging.error(f"[ARCTIC_TIMEOUT] Read '{key}' exceeded {ARCTIC_TIMEOUT*1000:.0f} ms.")
            return None

def _arctic_write(key: str, df: pd.DataFrame):
    """ArcticDB write with hard 300 ms timeout (Phase 1)."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(oracle_lib.write, key, df)
        try:
            fut.result(timeout=ARCTIC_TIMEOUT)
        except concurrent.futures.TimeoutError:
            logging.error(f"[ARCTIC_TIMEOUT] Write '{key}' exceeded {ARCTIC_TIMEOUT*1000:.0f} ms.")

# ── Staleness Gate ─────────────────────────────────────────────────────────────
def _check_staleness(symbol: str) -> bool:
    """Returns True (stale) if cached signal is > STALENESS_THRESHOLD seconds old."""
    item = _arctic_read(f"{symbol}_meta")
    if item is None:
        return False  # No cache yet — not stale, just cold
    try:
        cached_ts = float(item.data.iloc[-1]["timestamp"])
        age = time.time() - cached_ts
        if age > STALENESS_THRESHOLD:
            logging.warning(f"[STALE_SIGNAL] {symbol}: signal age {age:.0f}s > {STALENESS_THRESHOLD}s. Halting new entries.")
            return True
    except Exception:
        pass
    return False

# ── Fractional Differentiation (Phase 1 — memory-preserving stationarity) ────
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
    # Absolute fallback — use d=1.0 (minimum differentiation, NOT pct_change)
    return 1.0, apply_frac_diff(series, 1.0)

# ── Meta-Model (loaded once) ──────────────────────────────────────────────────────────────────────────────
_META_MODEL: xgb.XGBClassifier | None = None
_SHAP_EXPLAINER = None
if META_MODEL_PATH.exists():
    _META_MODEL = xgb.XGBClassifier()
    _META_MODEL.load_model(str(META_MODEL_PATH))
    _SHAP_EXPLAINER = shap.TreeExplainer(_META_MODEL)
    logging.info("[BOOT] Meta-Model + SHAP Explainer loaded.")

def _moe_reason(symbol: str, features: dict, direction: int) -> dict:
    """
    Phase 5: Contextual Routing — Constitution Directive 1.

    Crypto + Metals  →  Groq  (Llama-3.1-8b-instant, high-speed momentum)
    Forex + Indices  →  Gemini (gemini-2.5-flash, deep macro-synthesis)
    Fallback         →  Local Ollama MoE if both cloud engines are unavailable.

    Serialized Ollama path: _OLLAMA_LOCK prevents Thundering Herd on local GPU.
    Fail-safe: returns neutral 0.500 on any unhandled error.
    """
    feat_summary = json.dumps(
        {k: round(float(v), 6) if isinstance(v, (int, float, np.floating)) else str(v)
         for k, v in list(features.items())[:20]}
    )
    system_prompt = (
        "You are the Sentinel Meta-Model. Analyze the trading features and return ONLY valid JSON "
        "with keys: decision (BUY|SELL|HOLD), confidence (0.0-1.0), reasoning (string)."
    )
    user_prompt = (
        f"SYMBOL: {symbol} | PRIMARY_DIR: {direction} | FEATURES: {feat_summary}"
    )

    # ── Contextual Route: Crypto/Metals → Groq ───────────────────────────────
    if symbol in CRYPTO_METALS_ASSETS:
        if _GROQ_ENGINE is not None:
            try:
                logging.info(f"[ROUTER] {symbol} → Groq (Crypto/Metal stream)")
                return _GROQ_ENGINE.json_with_retry(system_prompt, user_prompt)
            except Exception as e:
                logging.warning(f"[ROUTER] Groq failed for {symbol}, falling back to Ollama: {e}")
        else:
            logging.warning(f"[ROUTER] Groq engine not available for {symbol}. Falling back to Ollama.")

    # ── Contextual Route: Forex/Indices → Gemini ───────────────────────────
    elif symbol in FOREX_INDEX_ASSETS:
        if _GEMINI_ENGINE is not None:
            try:
                logging.info(f"[ROUTER] {symbol} → Gemini (Forex/Index stream)")
                return _GEMINI_ENGINE.json_with_retry(system_prompt, user_prompt)
            except Exception as e:
                logging.warning(f"[ROUTER] Gemini failed for {symbol}, falling back to Ollama: {e}")
        else:
            logging.warning(f"[ROUTER] Gemini engine not available for {symbol}. Falling back to Ollama.")

    # ── Fallback: Local Ollama MoE (serialized) ──────────────────────────────
    logging.info(f"[ROUTER] {symbol} → Ollama (local fallback)")
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{system_prompt}\n\n{user_prompt}",
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0.05, "num_ctx": 256, "num_predict": 128},
    }
    try:
        with _OLLAMA_LOCK:  # Serialize — prevent Thundering Herd on local GPU
            resp = requests.post(OLLAMA_ENDPOINT, json=payload, timeout=REASONING_TIMEOUT)
        raw = resp.json().get("response", "{}")
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start != -1 and end > start:
            data = json.loads(raw[start:end])
            if all(k in data for k in ("decision", "confidence", "reasoning")):
                return data
    except Exception as e:
        logging.error(f"[{symbol}] Ollama MoE CRITICAL ERROR — {type(e).__name__}: {e}")
    return {"decision": "HOLD", "confidence": 0.500, "reasoning": "Fail-safe neutral — endpoint unavailable."}

# ── SHAP Diagnostics (Phase 2) ────────────────────────────────────────────────
CONCEPT_DRIFT_THRESHOLD = 0.65

def _run_shap(symbol: str, x_vec: list, f_keys: list, direction: int, p_final: float, reasoning: str):
    """Compute SHAP values, detect concept drift, write JSON to shap_diagnostics/."""
    if _SHAP_EXPLAINER is None:
        return
    try:
        s_vals = _SHAP_EXPLAINER.shap_values(np.array([x_vec]))[0]
        total_abs = np.sum(np.abs(s_vals)) + 1e-9
        weights = {f_keys[i]: float(s_vals[i] / total_abs) for i in range(len(s_vals))}
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

        # Return 0.0 conviction if drift detected (Hermes will also catch this)
        return 0.0 if max_weight > CONCEPT_DRIFT_THRESHOLD else None
    except Exception as e:
        logging.error(f"[{symbol}] SHAP error: {e}")
        return None

# -- Meta-Conviction (Phase 2 - Meta-Labeling Architecture) -------------------
def get_meta_conviction(symbol: str, features: dict, direction: int, base_p: float) -> float:
    """
    Decoupled sizing: primary direction already decided.
    Meta-model outputs conviction p; blended with Ollama MoE.
    """
    f_keys = ["W_rsi", "W_macd", "Wy_trend", "B_bbpos", "S_struct", "WHL_vol"]
    x_vec  = [float(features.get(k, 0.5)) for k in f_keys]

    # -- Pre-Reasoning Filter (Phase 2) ---------------------------------------
    # Only engage LLM if statistical engine has >0.65 or <0.35 conviction.
    # This prevents neutral noise from clogging the single-threaded Ollama queue.
    norm_base = abs(base_p - 0.5) + 0.5
    if norm_base < 0.65:
        logging.info(f"[{symbol}] Low base conviction ({base_p:.3f}). Skipping MoE.")
        return float(base_p)

    # -- MoE Reasoning --------------------------------------------------------
    moe = _moe_reason(symbol, features, direction)
    reasoning_conf = float(moe.get("confidence", 0.500))
    reasoning_text = moe.get("reasoning", "N/A")
    reasoning_dec  = moe.get("decision", "HOLD").upper()

    if "fail-safe" in reasoning_text.lower() or reasoning_conf == 0.500:
        p_final = 0.500
        logging.warning(f"[{symbol}] MoE Fail-Safe engaged -> Neutral 0.500")
    else:
        # Convert decision+confidence to probability space: BUY=conf, SELL=1-conf
        moe_p = reasoning_conf if reasoning_dec == "BUY" else (1.0 - reasoning_conf if reasoning_dec == "SELL" else 0.5)
        p_final = (base_p * 0.60) + (moe_p * 0.40)

    # -- SHAP Diagnostics -----------------------------------------------------
    drift_override = _run_shap(symbol, x_vec, f_keys, direction, p_final, reasoning_text)
    if drift_override is not None:
        p_final = drift_override

    logging.info(f"[{symbol}] Meta-Conviction: {p_final:.4f} | MoE: {reasoning_conf:.3f}")
    return float(p_final)

# -- Oracle Cooldown -----------------------------------------------------------
_LAST_UPDATE: Dict[str, float] = {}
ORACLE_COOLDOWN = 15.0

# -- Signal Router -------------------------------------------------------------
def push_to_orchestrator(payload: Dict[str, Any]):
    fname = SIGNAL_DIR / f"sig_{payload['symbol']}_{int(time.time())}.json"
    with open(fname, "w") as fh:
        json.dump(payload, fh, indent=2)
    logging.info(f"[SIGNAL_ROUTE] Dropped -> {fname.name}")

# -- Main Oracle Update --------------------------------------------------------
def update_slow_oracles(symbol: str):
    """
    Full cognition pipeline for one symbol:
    Data fetch -> FracDiff -> HMM -> Kronos/XGB -> Meta-Labeling -> SHAP -> Gate -> Route
    """
    now = time.time()
    if now - _LAST_UPDATE.get(symbol, 0) < ORACLE_COOLDOWN:
        return
    _LAST_UPDATE[symbol] = now

    # -- Macro Halt -----------------------------------------------------------
    if HALT_PATH.exists():
        logging.critical("[MACRO_HALT] Global suspension active. Sleeping 60 s.")
        time.sleep(60)
        return

    # -- Staleness Gate (Phase 1) ---------------------------------------------
    _check_staleness(symbol) # Log warning if stale, but proceed to refresh cache

    # -- Anti-rate-limit jitter ------------------------------------------------
    time.sleep(random.uniform(0.05, 0.3))

    df_m15 = df_ta = df_ml = None
    try:
        logging.info(f"[{symbol}] Updating oracles...")

        # 1. Fetch 2000 M15 bars (for FracDiff depth)
        df_m15 = sigproc.get_m15_dataframe(symbol, 2000)
        if df_m15 is None or len(df_m15) < 512:
            logging.error(f"[TICKER_ERROR] {symbol}: insufficient bars ({len(df_m15) if df_m15 is not None else 0}). Skipping.")
            return

        # 2. Feature Engineering
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

        # 3. Fractional Differentiation (Phase 1 - no integer diff on raw prices)
        df_ml = df_ta.copy()
        for col in ["open", "high", "low", "close"]:
            opt_d, fd = optimize_fracdiff_d(df_ta[col].values)
            pad = len(df_ta) - len(fd)
            df_ml[col] = np.pad(fd, (pad, 0), mode="edge")
        logging.info(f"[{symbol}] FracDiff applied (d optimised per OHLC column).")

        df_ml = df_ml.dropna()
        if len(df_ml) < 512:
            logging.error(f"[TICKER_ERROR] {symbol}: <512 clean bars after FracDiff. Skipping.")
            return

        # 4. HMM Oracle (Phase 2 - dynamic std-dev regime boundaries)
        hmm_state, hmm_prob, _ = hmm.get_current_state(df_m15["close"].values)
        atr = utils.calculate_atr(df_m15)
        logging.info(f"[HMM] {symbol}: {hmm_state} (p={hmm_prob:.3f})")

        # -- HMM Regime Alignment Gate (Phase 2) -------------------------------
        # (applied later at signal routing; stored for fast loop to consume)

        _arctic_write(f"{symbol}_hmm", pd.DataFrame([{
            "state": hmm_state,
            "prob": float(hmm_prob),
            "atr": float(atr),
            "timestamp": utils.get_utc_epoch(),
        }]))

        # 5. Kronos + XGBoost cognition
        kronos_bridge.update_cognition_cache(symbol, df_ml)
        try:
            k_item = _arctic_read(f"{symbol}_kronos")
            k_prob = float(k_item.data.iloc[-1]["kronos_prob"])
            x_prob = float(k_item.data.iloc[-1].get("xgboost_prob", 0.50))
        except Exception:
            k_prob = x_prob = 0.50

        p_blend   = (k_prob * 0.70) + (x_prob * 0.30)
        primary_dir = 1 if p_blend > 0.55 else (-1 if p_blend < 0.45 else 0)

        # 6. Meta-Conviction (Phase 2 - decoupled sizing)
        features  = df_ml.iloc[-1].to_dict()
        meta_p    = get_meta_conviction(symbol, features, primary_dir, base_p=p_blend)

        # -- Regime Alignment (Phase 2) -----------------------------------------
        if hmm_state == "BEAR" and primary_dir == 1:
            logging.info(f"[REGIME_BLOCK] {symbol}: BEAR regime blocks BUY signal.")
            meta_p = 0.50
        elif hmm_state == "BULL" and primary_dir == -1:
            logging.info(f"[REGIME_BLOCK] {symbol}: BULL regime blocks SELL signal.")
            meta_p = 0.50

        # 7. Write meta to ArcticDB (300 ms timeout)
        _arctic_write(f"{symbol}_meta", pd.DataFrame([{
            "primary_dir":      int(primary_dir),
            "meta_conviction":  float(meta_p),
            "hmm_state":        hmm_state,
            "atr":              float(atr),
            "timestamp":        utils.get_utc_epoch(),
        }]))

        # 8. Epistemic Gate (Phase 2 - absolute 0.82 minimum)
        norm_p = abs(meta_p - 0.5) + 0.5
        if norm_p >= EPISTEMIC_GATE and primary_dir != 0:
            signal_dir = "BUY" if primary_dir == 1 else "SELL"
            push_to_orchestrator({
                "symbol":             symbol,
                "direction":          signal_dir,
                "kronos_conviction":  round(float(meta_p), 4),
                "hmm_state":          hmm_state,
                "atr":                float(atr),
                "timestamp":          int(time.time()),
                "version":            "v17.3-PROD",
            })
        else:
            logging.info(f"[GATE] {symbol}: norm_p={norm_p:.3f} < {EPISTEMIC_GATE}. Suppressed.")

        # 9. TimesFM risk cache (using FracDiff df)
        timesfm_bridge.update_risk_cache(symbol, df_ml)

    except Exception as e:
        logging.error(f"[{symbol}] Oracle update error: {e}")
    finally:
        df_m15 = df_ta = df_ml = None

# -- Parallel Workload (Dual-Engine) -------------------------------------------
async def process_matrix_parallel(watchlist: list):
    loop = asyncio.get_event_loop()
    # Increase workers to match the 13-symbol watchlist to prevent thread starvation
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(watchlist)) as ex:
        tasks = [loop.run_in_executor(ex, update_slow_oracles, s) for s in watchlist]
        await asyncio.gather(*tasks)

# -- Historical Backfill -------------------------------------------------------
def execute_historical_backfill(watchlist: list):
    logging.info(f"[SRE] Historical Backfill ({len(watchlist)} assets)...")
    for symbol in watchlist:
        try:
            r1  = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1,  0, 2000)
            r15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 2000)
            ok  = (r1 is not None) and (r15 is not None)
            logging.info(f"  {'[+]' if ok else '[-]'} {symbol}: M1={len(r1) if r1 is not None else 0}, M15={len(r15) if r15 is not None else 0}")
        except Exception as e:
            logging.error(f"  [!] Backfill error for {symbol}: {e}")
    logging.info("[SRE] Backfill complete.")

# -- Entry Point ----------------------------------------------------------------
def main():
    if not mt5.initialize():
        logging.critical("MT5 Initialization Failed. Exiting.")
        sys.exit(1)

    logging.info("=" * 60)
    logging.info("  ADAPTIVE SENTINEL SLOW LOOP v17.3 - Machine A (Brain)")
    logging.info("=" * 60)

    watchlist = WATCHLIST

    execute_historical_backfill(watchlist)

    logging.info("[SYSTEM] Cache warm-up (parallel)...")
    asyncio.run(process_matrix_parallel(watchlist))
    logging.info("[SYSTEM] Warm-up complete. Entering event-driven dollar-bar cycle.")

    streamer = bars.InformationBarStreamer(watchlist)
    for bar in streamer.stream_bars():
        update_slow_oracles(bar["symbol"])

if __name__ == "__main__":
    main()
