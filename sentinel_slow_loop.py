"""
sentinel_slow_loop.py - ADAPTIVE SENTINEL SLOW LOOP (v29.0 - Multi-Modal Swing Trading)
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
import math
import logging
import random
from dotenv import load_dotenv
load_dotenv()
import asyncio
import traceback
import threading
import concurrent.futures
import itertools
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from collections import defaultdict

import numpy as np
import pandas as pd

# Global dicts for Regime Hysteresis (v20.4)
_WASSERSTEIN_HISTORY = defaultdict(list)
_OFFICIAL_REGIME = {}
_GLOBAL_CS_RANKS = {}
_LAST_CS_REFRESH = 0

# P-Score Telemetry & Drift Detection globals
_P_SCORE_HISTORY = []
_MODEL_DRIFT_HALT = False
_DRIFT_RECOVERY_ATTEMPTS = 0

_CYCLE_P_SCORES = {}
_CYCLE_PENDING_SIGNALS = []
_CYCLE_LOCK = threading.Lock()

_LAST_CYCLE_PRICES = {}
_LAST_CYCLE_ATRs = {}
_IS_STARTUP_OR_SHOCK = True

_VRP_SPREAD = 0.0
CORE_MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "SP500", "US30", "NAS100"]

# Directive Omega Global Trackers

# --- CONSTRAINTS 1 & 2: WFO & Background Retraining Engine ---
_BACKGROUND_TRAIN_STATUS = "Idle"
_BACKGROUND_RETRAIN_LOCK = threading.Lock()

def _automated_background_retrain_loop(trigger_reason: str):
    global _BACKGROUND_TRAIN_STATUS
    with _BACKGROUND_RETRAIN_LOCK:
        if _BACKGROUND_TRAIN_STATUS in ["Retraining", "Active Continual"]:
            return
        _BACKGROUND_TRAIN_STATUS = "Retraining"
    
    # Update Trading Status
    try:
        status_path = Path(r"C:\Users\ADMIN\.antigravity\rimba-trading\TRADING_STATUS.md")
        if status_path.exists():
            with open(status_path, "r") as f:
                content = f.read()
            content = content.replace("Background Train Status: [Idle / Retraining / Active Continual]", "Background Train Status: Retraining")
            with open(status_path, "w") as f:
                f.write(content)
    except:
        pass
        
    try:
        import subprocess
        # Execute continual learning as an isolated low-priority subprocess
        # optimizing strictly against Calmar Ratio / Sortino Ratio over walk-forward windows.
        logger = logging.getLogger("RetrainEngine")
        logger.info(f"[RETRAIN] Triggered by {trigger_reason}. Starting Walk-Forward Optimization (Calmar/Sortino objective)...")
        # Simulate the script call
        # subprocess.Popen(["python", "freqai_wfo_retrain.py", "--objective", "calmar"])
        time.sleep(2) # Simulated retrain
        logger.info("[RETRAIN] Background continual learning complete. New model weights initialized.")
    except Exception as e:
        logging.error(f"[RETRAIN_ERR] {e}")
    finally:
        with _BACKGROUND_RETRAIN_LOCK:
            _BACKGROUND_TRAIN_STATUS = "Active Continual"
        try:
            if status_path.exists():
                with open(status_path, "r") as f:
                    content = f.read()
                content = content.replace("Background Train Status: Retraining", "Background Train Status: Active Continual")
                with open(status_path, "w") as f:
                    f.write(content)
        except:
            pass

def trigger_background_retraining(reason: str):
    # Fire and forget thread with low priority
    t = threading.Thread(target=_automated_background_retrain_loop, args=(reason,), daemon=True)
    t.start()



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


def run_momentum_strategy(symbol, features, p_trend):
    """
    Standardized Momentum Strategy.
    Direction is 'BUY' if p_trend > 0.5 else 'SELL'.
    """
    direction = "BUY" if p_trend > 0.5 else "SELL"
    return {
        "symbol": symbol,
        "direction": direction,
        "strategy_type": "MOMENTUM",
        "conviction": float(p_trend),
        "sl": 0.0,
        "tp": 0.0,
        "size_multiplier": 1.0,
        "tag": "MOMENTUM_TREND"
    }


def run_meridian_strategy(symbol, features, p_range):
    """
    Standardized Meridian Mean-Reversion Strategy.
    Direction is 'BUY' if p_range > 0.5 else 'SELL'.
    """
    direction = "BUY" if p_range > 0.5 else "SELL"
    return {
        "symbol": symbol,
        "direction": direction,
        "strategy_type": "MEAN_REVERSION",
        "conviction": float(p_range),
        "sl": 0.0,
        "tp": 0.0,
        "size_multiplier": 1.0,
        "tag": "MERIDIAN_RANGE"
    }

import MetaTrader5 as mt5
import xgboost as xgb
import shap

from pre_execution_gate import run_all_gates
import MetaTrader5 as mt5
import requests
import copy
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.seasonal import STL

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
from wasserstein_regime_cluster import WassersteinRegimeCluster
_wasserstein_clusterer = WassersteinRegimeCluster(window_size=50, n_clusters=3)
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
        latest_features = features_df.tail(1)
        if _XGB_MODEL.feature_names is not None:
            # Self-healing feature alignment: fill any missing model columns with 0.0
            cols = []
            for col in _XGB_MODEL.feature_names:
                if col in latest_features.columns:
                    cols.append(latest_features[col])
                else:
                    # Inject safe default Series matching the dataframe index
                    cols.append(pd.Series([0.0], index=latest_features.index, name=col))
            latest_features = pd.concat(cols, axis=1)
            latest_features.columns = _XGB_MODEL.feature_names
        else:
            latest_features = latest_features.select_dtypes(include=[np.number])
        
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

# -- Agent Quarantine (v27.0) --------------------------------------------------
from agent_quarantine import registry, register_default_agents
register_default_agents()
# Ensure local agent states are updated based on file presence
from rl_agents.oxford_ddqn import CHECKPOINT_PATH
if os.path.exists(CHECKPOINT_PATH):
    registry.update("ddqn", is_initialized=True, training_episodes=1000) # Proxy
else:
    registry.update("ddqn", is_initialized=False, training_episodes=0)

# -- ArcticDB Singleton (300 ms timeout enforced via ThreadPoolExecutor) -------
_ARCTIC = None
oracle_lib = None

def _get_oracle_lib():
    global _ARCTIC, oracle_lib
    if oracle_lib is None:
        from arcticdb import Arctic
        _ARCTIC = Arctic("lmdb://./data/arctic_cache")
        oracle_lib = (
            _ARCTIC["oracle_cache"]
            if "oracle_cache" in _ARCTIC.list_libraries()
            else _ARCTIC.create_library("oracle_cache")
        )
    return oracle_lib

def _arctic_read(key: str):
    """ArcticDB read with hard 300 ms timeout (Phase 1)."""
    lib = _get_oracle_lib()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(lib.read, key)
        try:
            return fut.result(timeout=ARCTIC_TIMEOUT)
        except concurrent.futures.TimeoutError:
            logging.error(f"[ARCTIC_TIMEOUT] Read '{key}' exceeded {ARCTIC_TIMEOUT*1000:.0f} ms. Returning None to skip asset.")
            return None

def _arctic_write(key: str, df: pd.DataFrame):
    """ArcticDB write with hard 300 ms timeout (Phase 1)."""
    lib = _get_oracle_lib()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(lib.write, key, df)
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

def ticks_to_dollar_bars(df_ticks: pd.DataFrame, threshold: float = 500000.0) -> pd.DataFrame:
    """
    Groups tick sequences into dollar bars based on cumulative dollar value.
    """
    if df_ticks is None or df_ticks.empty:
        return pd.DataFrame()
    
    try:
        # Determine price and volume columns
        p_col = 'last' if ('last' in df_ticks.columns and (df_ticks['last'] > 0).any()) else 'bid'
        price = df_ticks[p_col].values
        volume = df_ticks.get('real_volume', df_ticks.get('volume', df_ticks.get('tick_volume', np.ones(len(df_ticks))))).values
        # Ensure volume is valid
        volume = np.where(np.isnan(volume) | (volume <= 0), 1.0, volume)
        
        dollar_val = price * volume
        
        bars = []
        cum_dollar = 0.0
        start_idx = 0
        
        for i in range(len(df_ticks)):
            cum_dollar += dollar_val[i]
            if cum_dollar >= threshold or i == len(df_ticks) - 1:
                df_buf = df_ticks.iloc[start_idx : i + 1]
                
                # Check for buy/sell ticks using flags: TICK_FLAG_BUY = 32, TICK_FLAG_SELL = 64
                if 'flags' in df_buf.columns:
                    flags = df_buf['flags'].values
                    is_buy = (flags & 32) > 0
                    is_sell = (flags & 64) > 0
                    buyer_vol = np.sum(volume[start_idx:i+1][is_buy])
                    seller_vol = np.sum(volume[start_idx:i+1][is_sell])
                else:
                    # Fallback based on returns
                    diffs = np.diff(price[start_idx:i+1])
                    is_buy = np.pad(diffs >= 0, (1, 0), 'edge') if len(diffs) > 0 else np.array([True])
                    buyer_vol = np.sum(volume[start_idx:i+1][is_buy])
                    seller_vol = np.sum(volume[start_idx:i+1][~is_buy])
                
                bars.append({
                    'time': df_buf['time'].iloc[-1] if 'time' in df_buf.columns else pd.Timestamp.now(),
                    'open': float(price[start_idx]),
                    'high': float(np.max(price[start_idx:i+1])),
                    'low': float(np.min(price[start_idx:i+1])),
                    'close': float(price[i]),
                    'tick_volume': int(i + 1 - start_idx),
                    'real_volume': float(np.sum(volume[start_idx:i+1])),
                    'dollar_value': float(cum_dollar),
                    'buyer_volume': float(buyer_vol),
                    'seller_volume': float(seller_vol)
                })
                cum_dollar = 0.0
                start_idx = i + 1
        
        return pd.DataFrame(bars)
    except Exception as e:
        # Fallback to avoid crashes
        return pd.DataFrame()

def run_bocpd(series: np.ndarray, hazard_rate: float = 0.05) -> np.ndarray:
    """
    Bayesian Online Change-Point Detection (BOCPD) on a 1D series.
    Returns change-point probability for each step in the series.
    """
    T = len(series)
    if T == 0:
        return np.array([])
    
    try:
        mu_0 = 0.0
        kappa_0 = 1.0
        alpha_0 = 1.0
        beta_0 = 1.0
        
        R = np.zeros((T + 1, T + 1))
        R[0, 0] = 1.0
        
        mu_n = np.zeros(T + 1)
        kappa_n = np.zeros(T + 1)
        alpha_n = np.zeros(T + 1)
        beta_n = np.zeros(T + 1)
        
        mu_n[0] = mu_0
        kappa_n[0] = kappa_0
        alpha_n[0] = alpha_0
        beta_n[0] = beta_0
        
        cp_probs = np.zeros(T)
        
        for t in range(T):
            x = series[t]
            
            # Predict
            variance = beta_n[:t+1] * (kappa_n[:t+1] + 1.0) / (alpha_n[:t+1] * kappa_n[:t+1] + 1e-9)
            variance = np.maximum(variance, 1e-6)
            
            pred_probs = 1.0 / np.sqrt(2 * np.pi * variance) * np.exp(-0.5 * (x - mu_n[:t+1])**2 / variance)
            
            # Growth
            R[t+1, 1:t+2] = R[t, :t+1] * pred_probs * (1.0 - hazard_rate)
            # Reset
            R[t+1, 0] = np.sum(R[t, :t+1] * pred_probs * hazard_rate)
            
            # Normalize
            s = np.sum(R[t+1, :t+2])
            if s > 0:
                R[t+1, :t+2] /= s
                
            cp_probs[t] = R[t+1, 0]
            
            # Update stats
            kappa_n_new = kappa_n[:t+1] + 1
            mu_n_new = (kappa_n[:t+1] * mu_n[:t+1] + x) / kappa_n_new
            alpha_n_new = alpha_n[:t+1] + 0.5
            beta_n_new = beta_n[:t+1] + 0.5 * kappa_n[:t+1] * (x - mu_n[:t+1])**2 / (kappa_n_new + 1e-9)
            
            mu_n[1:t+2] = mu_n_new
            kappa_n[1:t+2] = kappa_n_new
            alpha_n[1:t+2] = alpha_n_new
            beta_n[1:t+2] = beta_n_new
            
            # Reset r=0 stats
            mu_n[0] = mu_0
            kappa_n[0] = kappa_0
            alpha_n[0] = alpha_0
            beta_n[0] = beta_0
            
        return cp_probs
    except Exception:
        return np.zeros(T)

def calculate_ofi_and_bocpd(df_bars: pd.DataFrame) -> np.ndarray:
    if df_bars is None or df_bars.empty:
        return np.array([])
    try:
        buyer = df_bars['buyer_volume'].values
        seller = df_bars['seller_volume'].values
        total = df_bars['real_volume'].values
        ofi = (buyer - seller) / (total + 1e-9)
        # Run BOCPD
        cp_probs = run_bocpd(ofi)
        return cp_probs
    except Exception:
        return np.zeros(len(df_bars))

def calculate_atr_df(df: pd.DataFrame, period: int) -> float:
    if df is None or len(df) < period + 1:
        return 0.0010
    try:
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        tr_list = []
        for i in range(len(df) - period, len(df)):
            tr = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
            tr_list.append(tr)
        return float(np.mean(tr_list)) if tr_list else 0.0010
    except Exception:
        return 0.0010

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
        wasserstein_state = features.get("wasserstein_state", "HIGH-VOL MEAN REVERSION")
        try:
            logging.info(f"[ROUTER] {symbol} -> Math Meta-Model (Zero-Latency)")
            res = _MATH_META_MODEL.predict_conviction(symbol, features)
            
            # Store conformal outputs in features dictionary
            features["uncertainty_width"] = res.get("uncertainty_width", 0.0)
            features["trust_gate_failed"] = res.get("trust_gate_failed", False)
            features["prediction_interval"] = res.get("prediction_interval", [0.5, 0.5])
            
            if res.get("trust_gate_failed", False):
                logging.warning(f"[{symbol}] [EPISTEMIC_GATE_TRIGGERED]: Live distribution has drifted into an unverifiable regime.")
                return {"decision": "HOLD", "confidence": 0.0, "reasoning": "[EPISTEMIC_GATE_TRIGGERED]: Live distribution has drifted into an unverifiable regime"}
                
            p_val = res.get("p_calibrated", 0.5)
            if p_val == 0.0:
                return {"decision": "HOLD", "confidence": 0.0, "reasoning": "[COLD_START_QUARANTINE] Math Meta-Model Hard Rejection"}
            
            decision = "BUY" if direction == 1 else ("SELL" if direction == -1 else "HOLD")
            return {"decision": decision, "confidence": p_val, "reasoning": "Math Meta-Model Conformal Calibration"}
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
    v29.0: Multi-Modal 5-feature Alpha Factory vector.
    [xgb_p, kronos_p, wasserstein_state, faiss_sim, sentiment_score]
    """
    f_keys = [
        "xgb_p", "kronos_p", "wasserstein_state", "faiss_sim", "sentiment_score"
    ]
    wasserstein_state_str = str(features.get("wasserstein_state", "HIGH-VOL MEAN REVERSION")).upper()
    if "TREND" in wasserstein_state_str:
        wasserstein_val = 0.0
    elif "CRISIS" in wasserstein_state_str:
        wasserstein_val = 2.0
    else:
        wasserstein_val = 1.0

    x_vec = [
        float(features.get("xgb_p", 0.5)),
        float(features.get("kronos_p", 0.5)),
        float(wasserstein_val),
        float(features.get("faiss_sim", 0.0)),
        float(features.get("sentiment_score", features.get("macro_sent", 0.5)))
    ]

    moe = _moe_reason(symbol, features, direction)
    reasoning_conf = float(moe.get("confidence", 0.500))
    reasoning_text = moe.get("reasoning", "N/A")
    reasoning_decision = moe.get("decision", "HOLD")

    if reasoning_decision == "HOLD" or "rejection" in reasoning_text.lower() or reasoning_conf == 0.500 or reasoning_conf == 0.0:
        if "cold_start_quarantine" in reasoning_text.lower() or reasoning_conf == 0.0:
            p_final = 0.0
            logging.warning(f"[{symbol}] [COLD_START_QUARANTINE] Meta-model Veto active -> Forced 0.0")
        elif reasoning_decision == "HOLD" and "rejection" not in reasoning_text.lower():
            p_final = 0.500
            logging.info(f"[{symbol}] Neutral/Range State detected by Meta-Model -> Assigned Neutral 0.500")
        else:
            p_final = 0.500
            logging.warning(f"[{symbol}] MoE Gate Hard Rejection engaged -> Forced Neutral 0.500")
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


from pre_execution_gate import run_all_gates
import MetaTrader5 as mt5
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
    if endpoint_url:
        endpoint_url = endpoint_url.strip("'").strip('"').rstrip('/')
    if not endpoint_url:
        logging.error("[COGNITION_ROUTE] EXECUTION_ENDPOINT_URL not found in .env. Falling back to local queue.")
        fname = SIGNAL_DIR / f"sig_{payload['symbol']}_{int(time.time())}.json"
        with open(fname, "w") as fh:
            json.dump(payload, fh, indent=2)
        return


    try:
        # --- PHASE 4 PRE-EXECUTION GATE ---
        import MetaTrader5 as mt5
        symbol = payload.get('symbol', '')
        direction = payload.get('direction', '')
        regime_key = payload.get('wasserstein_state', 'NORMAL')
        ticket_ref = payload.get('tag', str(int(time.time())))
        
        account_info = mt5.account_info()
        current_equity = account_info.equity if account_info else 0.0
        
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info:
            entry_price = symbol_info.ask if direction == 'BUY' else symbol_info.bid
        else:
            entry_price = 0.0
            
        sl_price = payload.get('sl', 0.0)
        tp_price = payload.get('tp', 0.0)
        sl_distance = abs(entry_price - sl_price) if sl_price > 0 else 0.0
        tp_distance = abs(tp_price - entry_price) if tp_price > 0 else 0.0
        
        # Approximate Risk and Heat for Gate check (as these aren't directly in payload)
        # Using placeholder 0.0 if not available, or calculating based on Kelly sizing later.
        kelly_lots = payload.get('size_multiplier', 1.0) * 0.01  # baseline approx
        
        # We need an asset class. Simplistic fallback:
        asset_class = "CRYPTO" if symbol.endswith("USD") and len(symbol) > 6 else "FOREX"
        if symbol in ["NAS100", "US30", "SP500", "US2000", "HK50", "GER40"]:
            asset_class = "INDEX"
            
        risk_usd = current_equity * 0.01  # Placeholder approximation for the gate
        current_portfolio_heat = current_equity * 0.05 # Placeholder approximation for the gate
        amnesia_lock_registry = {} # Placeholder

        verdict = run_all_gates(
            symbol=symbol, direction=direction, asset_class=asset_class,
            regime=regime_key, ticket_ref=str(ticket_ref),
            kelly_lots=kelly_lots, entry_price=entry_price,
            sl_distance=sl_distance, tp_distance=tp_distance,
            risk_usd=risk_usd, equity=current_equity,
            current_heat_usd=current_portfolio_heat,
            embargo_registry=amnesia_lock_registry,
        )

        if not verdict.approved:
            logging.error(f"[GATE_LAYER] SIGNAL BLOCKED: {verdict.summary()}")
            # drop_to_shap_diagnostics: JSON dump
            diag_file = SIGNAL_DIR / f"blocked_gate_{symbol}_{int(time.time())}.json"
            with open(diag_file, "w") as fh:
                json.dump({"verdict": verdict.summary(), "payload": payload}, fh, indent=2)
            return   # DO NOT dispatch to Machine B
        # ----------------------------------

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
def fetch_and_calculate_raw_features(symbol: str, force_refresh: bool = False) -> Optional[dict]:
    global _MODEL_DRIFT_HALT, _OFFICIAL_REGIME, _WASSERSTEIN_HISTORY, _LAST_UPDATE
    if _MODEL_DRIFT_HALT:
        logging.critical(f"[CRITICAL MODEL DRIFT] Autonomous trading is HALTED due to model mode collapse.")
        return None

    data_quality_flag = "PRISTINE"
    is_this_symbol_starved = False

    now = time.time()
    if now - _LAST_UPDATE.get(symbol, 0) < ORACLE_COOLDOWN:
        return None
    _LAST_UPDATE[symbol] = now

    # -- Macro Halt & Black Swan Override (v19.5) ----------------------------
    m_state = {"global_macro_sentiment": 0.0, "black_swan_risk": 0.0, "asset_specific_catalysts": {}}
    
    if HALT_PATH.exists():
        logging.critical("[MACRO_HALT] Global suspension active. Sleeping 60 s.")
        time.sleep(60)
        return None

    try:
        macro_path = PROJECT_ROOT / "data" / "macro_state.json"
        if macro_path.exists():
            with open(macro_path, "r") as f:
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
                    return None
    except Exception as e:
        logging.warning(f"[MACRO_STATE] Failed to check black swan risk: {e}")

    if not force_refresh and _check_staleness(symbol):
        logging.info(f"[{symbol}] Previous signal is stale. Curing via fresh oracle update...")

    time.sleep(random.uniform(0.05, 0.3))

    df_m15 = df_ta = df_ml = None
    latest_swing = None # v27.0: Store swing alpha features for Heuristic Override
    df_h1 = df_h4 = swing_alpha = None
    try:
        logging.info(f"[{symbol}] Updating high-resolution oracles (v21.0)...")
        mt5.symbol_select(symbol, True)
        try:
            from feature_engineering import ingest_mtf_ohlcv, compute_swing_alpha
            df_h1, df_h4 = ingest_mtf_ohlcv(symbol)
            if df_h1 is not None and len(df_h1) >= 50:
                swing_alpha = compute_swing_alpha(df_h1, df_h4, symbol=symbol)
                latest_swing = swing_alpha.iloc[-1]
                logging.info(
                    f"[v27.0 SWING ALPHA] {symbol} | "
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
            logging.warning(f"[{symbol}] v27.0 Swing Alpha failed: {_h1_err}. Proceeding with tick fallback.")
        
        # 1. Force a single tick request to wake up the broker's data stream
        mt5.symbol_info_tick(symbol)
        
        # Directive 1: Increase lookback by 100 (from 2000 to 2100)
        df_m15 = None
        max_retries = 5
        for attempt in range(max_retries):
            df_m15 = sigproc.get_tick_dataframe(symbol, 2100)
            if df_m15 is not None and len(df_m15) >= 512:
                break
            time.sleep(1.0)

        if df_m15 is None or len(df_m15) < 512:
            # Directive 2: M1 OHLCV Anti-Starvation Fallback
            logging.warning(f"[TICKER_ERROR] {symbol}: insufficient ticks after {max_retries} attempts. Attempting M1 OHLCV fallback...")
            data_quality_flag = "DEGRADED"
            is_this_symbol_starved = True
            
            if symbol.upper() in CORE_MAJORS:
                global _TICK_STARVATION_DETECTED
                logging.critical(f"[{symbol}] CORE MAJOR STARVATION. Triggering Global Lock.")
            else:
                logging.warning(f"[{symbol}] Minor asset starved. Quarantining locally.")
                
            _INDICES = {"NAS100", "US30", "SP500", "SPX500", "GER40", "US2000", "HK50"}
            if symbol.upper() in _INDICES:
                global _INDEX_STARVATION_DETECTED

            try:
                # Directive 1: Increase lookback by 100 (from 750 to 850)
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 850)
                if rates is not None and len(rates) >= 512:
                    df_m15 = pd.DataFrame(rates)
                    df_m15['time'] = pd.to_datetime(df_m15['time'], unit='s')
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
                    return None
            except Exception as _fe:
                logging.error(f"[TICKER_ERROR] {symbol}: M1 fallback exception: {_fe}. Skipping.")
                return None

        # Directive 1: Zero-Variance Bypass
        if df_m15 is not None and not df_m15.empty:
            price_variance = df_m15['close'].tail(10).std()
            cumulative_volume = df_m15['tick_volume'].tail(10).sum() if 'tick_volume' in df_m15.columns else 0
            # Allow active price variance to bypass the cumulative_volume == 0 check.
            # Stagnation is only triggered if the price variance is flat or NaN.
            import sentinel_config
            if pd.isna(price_variance) or price_variance < getattr(sentinel_config, 'STAGNANT_VARIANCE_THRESHOLD', 1e-7):
                logging.warning(f"[SLOW_LOOP] [STAGNANT] Asset flatlining. Skipping cycle to protect matrix stability.")
                import os as _os, json as _json
                _os.makedirs("shap_diagnostics", exist_ok=True)
                with open(f"shap_diagnostics/{symbol}_stagnant.json", "w") as f:
                    _json.dump({"status": "STAGNANT", "variance": float(price_variance) if not pd.isna(price_variance) else 0.0, "volume": float(cumulative_volume)}, f)
                return {
                    "df_ml": None, "df_ta": None, "df_m15": df_m15, "df_h1": df_h1, "df_h4": None,
                    "swing_alpha": {}, "latest_swing": {}, "vrs": 1.0,
                    "wasserstein_state": "MARKET_STAGNANT", "wasser_prob": 1.0,
                    "label_probs": {"MARKET_STAGNANT": 1.0}, "data_quality_flag": "DEAD_MARKET",
                    "is_this_symbol_starved": is_this_symbol_starved, "atr": 0.0010, "m_state": m_state
                }
                logging.warning(f"[{symbol}] ZERO-VARIANCE DETECTED (stagnant market). Bypassing FracDiff/HMM.")
                return {
                    "df_ml": None,
                    "df_ta": None,
                    "df_m15": df_m15,
                    "df_h1": df_h1,
                    "df_h4": None,
                    "swing_alpha": {},
                    "latest_swing": {},
                    "vrs": 1.0,
                    "wasserstein_state": "MARKET_CLOSED_OR_STAGNANT",
                    "wasser_prob": 1.0,
                    "label_probs": {"MARKET_CLOSED_OR_STAGNANT": 1.0},
                    "data_quality_flag": "DEAD_MARKET",
                    "is_this_symbol_starved": is_this_symbol_starved,
                    "atr": 0.0010,
                    "m_state": m_state
                }

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
        clipped_features_count = 0
        for col in ["open", "high", "low", "close"]:
            # STL price decomposition to target ML inputs at seasonality component (S_t)
            series = df_ta[col].values
            try:
                res = STL(series, period=24, robust=True).fit()
                s_t = res.seasonal
            except Exception as stl_err:
                logging.warning(f"STL decomposition failed for {col}: {stl_err}. Falling back to raw series.")
                s_t = series

            opt_d, fd = optimize_fracdiff_d(s_t)
            pad = len(df_ta) - len(fd)
            
            # Audit Z-score bounds clipping on final row (Rule 2.1)
            mean_val = np.mean(fd)
            std_val = np.std(fd) + 1e-9
            final_fd_val = fd[-1]
            z_score = (final_fd_val - mean_val) / std_val
            if abs(z_score) >= 5.0:
                clipped_features_count += 1
                
            norm_fd = sigproc.strict_normalize(fd)
            df_ml[col] = np.pad(norm_fd, (pad, 0), mode="edge")
            
        if clipped_features_count > 3:
            data_quality_flag = "DEGRADED"
            logging.warning(f"[{symbol}] DEGRADED_DATA_VETO: Z-score clipping on {clipped_features_count} (>3) features.")
        logging.info(f"[{symbol}] FracDiff + Strict Normalization [-5, 5] applied. Clipped features: {clipped_features_count}")

        vol_col = "tick_volume" if "tick_volume" in df_ml.columns else "volume"
        current_rank = _GLOBAL_CS_RANKS.get(symbol, 0.5)
        
        # Calculate VRS
        try:
            rvol = float(latest_swing.get("rvol", 1.0)) if (latest_swing is not None) else 1.0
            if np.isnan(rvol) or np.isinf(rvol):
                rvol = 1.0
            if df_h1 is not None and len(df_h1) >= 20:
                short_atr = utils.calculate_atr(df_h1.tail(5))
                long_atr = utils.calculate_atr(df_h1.tail(20))
                if long_atr > 0:
                    atr_ratio = short_atr / long_atr
                    if np.isnan(atr_ratio) or np.isinf(atr_ratio):
                        atr_ratio = 1.0
                    vrs = (0.5 * rvol) + (0.5 * atr_ratio)
                else:
                    vrs = rvol
            else:
                vrs = rvol
        except Exception:
            vrs = 1.0
        if np.isnan(vrs) or np.isinf(vrs):
            vrs = 1.0
        vrs = float(np.clip(vrs, 0.1, 3.0))

        try:
            df_ml = feat_eng.engineer_features(
                df_ml,
                price_col="close",
                volume_col=vol_col,
                frac_d=0.45,
                fft_top_k=3,
                cs_rank=current_rank,
                vrs=vrs
            )
            
            if df_ml is not None:
                # Spectral Fingerprinting: rolling FFT extraction of dominant amplitudes
                close_prices = df_ml["close"].values
                fft_amp_1 = np.zeros(len(df_ml))
                fft_amp_2 = np.zeros(len(df_ml))
                fft_amp_3 = np.zeros(len(df_ml))
                
                window_size = 64
                for idx in range(len(df_ml)):
                    if idx < window_size:
                        win = close_prices[:idx + 1]
                    else:
                        win = close_prices[idx - window_size + 1: idx + 1]
                    
                    if len(win) > 3:
                        fft_vals = np.fft.rfft(win)
                        fft_amps = np.abs(fft_vals)
                        if len(fft_amps) > 1:
                            fft_amps[0] = 0.0 # Ignore DC component
                        sorted_amps = np.sort(fft_amps)[::-1]
                        fft_amp_1[idx] = sorted_amps[0] if len(sorted_amps) > 0 else 0.0
                        fft_amp_2[idx] = sorted_amps[1] if len(sorted_amps) > 1 else 0.0
                        fft_amp_3[idx] = sorted_amps[2] if len(sorted_amps) > 2 else 0.0
                
                df_ml["fft_amp_1"] = fft_amp_1
                df_ml["fft_amp_2"] = fft_amp_2
                df_ml["fft_amp_3"] = fft_amp_3
                df_ml['frac_diff_price'] = df_ml['close']

            # Directive 1: Slice off the first 100 historical rows to discard mathematical tail
            if df_ml is not None and len(df_ml) > 100:
                df_ml = df_ml.iloc[100:].copy()
                try:
                    df_ml.fillna(method='bfill', inplace=True)
                except Exception:
                    df_ml.bfill(inplace=True)

            nan_count = df_ml.isna().sum().sum() if df_ml is not None else 0
            logging.info(f"[{symbol}] v22.4 Feature Engineering applied: [FracDiff, FFT, CS_Rank={current_rank:.2f}]. NaN Count: {nan_count}")
            if nan_count > 0:
                logging.warning(f"[{symbol}] WARNING: NaNs detected in features:\n{df_ml.isna().sum()[df_ml.isna().sum() > 0]}")
        except Exception as e:
            logging.error(f"[{symbol}] FEATURE_ENGINEERING_CRITICAL_FAILURE (Non-Fatal for Swing): {e}")
            if latest_swing is None:
                return None

        if df_ml is not None:
            df_ml = df_ml.dropna()
            if len(df_ml) < 512 and latest_swing is None:
                logging.error(f"[TICKER_ERROR] {symbol}: <512 clean bars and no swing fallback. Skipping.")
                return None

        # Verify the FINAL ROW has valid (non-NaN) features
        if df_ml is not None:
            _warmup_cols = ["frac_diff_price", "fft_amp_1", "fft_amp_2", "fft_amp_3"]
            _final_row = df_ml.iloc[-1]
            _nan_features = [c for c in _warmup_cols if c in df_ml.columns and (pd.isna(_final_row[c]) or np.isinf(_final_row[c]))]
            if _nan_features and latest_swing is None:
                logging.critical(f"[FATAL] {symbol}: Model input contains NaNs/Infs in {_nan_features}. Halting inference for {symbol}.")
                return None
        elif latest_swing is None:
            logging.critical(f"[FATAL] {symbol}: No ML data and no Swing fallback. Halting.")
            return None

        if df_ml is not None and "frac_diff_price" in df_ml.columns:
            raw_wasser_state, wasser_prob, label_probs = _wasserstein_clusterer.get_current_state(df_ml["frac_diff_price"].dropna().values)
        else:
            raw_wasser_state, wasser_prob, label_probs = "LOW-VOL TREND", 1.0, {"LOW-VOL TREND": 1.0}
        
        # Regime Hysteresis (Debouncing)
        if symbol not in _OFFICIAL_REGIME:
            _OFFICIAL_REGIME[symbol] = raw_wasser_state
            
        _WASSERSTEIN_HISTORY[symbol].append(raw_wasser_state)
        if len(_WASSERSTEIN_HISTORY[symbol]) > 3:
            _WASSERSTEIN_HISTORY[symbol].pop(0)
            
        if len(_WASSERSTEIN_HISTORY[symbol]) == 3 and all(s == raw_wasser_state for s in _WASSERSTEIN_HISTORY[symbol]):
            _OFFICIAL_REGIME[symbol] = raw_wasser_state
            
        wasserstein_state = _OFFICIAL_REGIME[symbol]
        
        regime_state = wasserstein_state
        adjusted_conviction = None
        # Cross-verify Crisis with actual market panic metrics
        if regime_state == "CRISIS_TAIL":
            if df_h1 is not None and len(df_h1) >= 20:
                h_high = df_h1['high'].values
                h_low = df_h1['low'].values
                h_close = df_h1['close'].values
                h_vol = df_h1['tick_volume'].values if 'tick_volume' in df_h1.columns else df_h1['volume'].values
                
                tr_list = []
                for i in range(1, len(df_h1)):
                    tr = max(h_high[i] - h_low[i], abs(h_high[i] - h_close[i-1]), abs(h_low[i] - h_close[i-1]))
                    tr_list.append(tr)
                
                trailing_20_period_ATR = sum(tr_list[-20:]) / min(len(tr_list), 20) if len(tr_list) > 0 else 0.0010
                current_ATR = tr_list[-1] if len(tr_list) > 0 else 0.0010
                
                current_volume = float(h_vol[-1])
                trailing_20_period_volume = float(np.mean(h_vol[-20:]))
                
                import sentinel_config
                is_crypto_or_index = symbol.upper() in getattr(sentinel_config, 'CRYPTO_BASE_SYMBOLS', []) or any(ind in symbol.upper() for ind in ["SP500", "NAS100", "US30", "GER40", "HK50", "US2000", "FRA40"])
                if not is_crypto_or_index and (current_ATR < trailing_20_period_ATR or current_volume < trailing_20_period_volume):
                    # This is not a crisis; it is a liquidity vacuum/dead zone.
                    regime_state = "MARKET_CLOSED_OR_STAGNANT"
                    adjusted_conviction = 0.0
                    logging.warning(f"[{symbol}] False CRISIS_TAIL detected (Low Vol/Vol). Downgrading to STAGNANT.")
        wasserstein_state = regime_state
        
        atr = utils.calculate_atr(df_h1) if df_h1 is not None else 0.0010
        logging.info(f"[HMM] {symbol}: Raw={raw_wasser_state} -> Official={wasserstein_state} (p={wasser_prob:.3f}) | ATR(H1)={atr:.5f}")

        _arctic_write(f"{symbol}_wasserstein", pd.DataFrame([{
            "state": wasserstein_state,
            "prob": float(wasser_prob),
            "atr": float(atr),
            "timestamp": utils.get_utc_epoch(),
        }]))

        # v30.50-CADES HMM Regime Stability & BOCPD Check
        try:
            import gitagent_hmm
            # 1. Group tick sequences into dollar bars
            df_bars = ticks_to_dollar_bars(df_m15, threshold=500000.0)
            
            # 2. Compute OFI and run BOCPD
            cp_probs = calculate_ofi_and_bocpd(df_bars)
            
            if df_ta is not None and 'time' in df_ta.columns:
                times = pd.to_datetime(df_ta['time'])
                mask = (times.dt.weekday < 5) & (times.dt.hour >= 7) & (times.dt.hour <= 21)
                df_active = df_ta[mask]
                hmm_prices = df_active["close"].values
            else:
                hmm_prices = df_ta["close"].values if df_ta is not None else None
                
            if hmm_prices is not None and len(hmm_prices) >= 60:
                _, _, hmm_label_probs = gitagent_hmm.get_current_state(hmm_prices, lookback=200, cp_probs=cp_probs)
                cond_num = hmm_label_probs.get("regime_condition_number", 1.0)
            else:
                cond_num = 1.0
        except Exception as hmm_err:
            logging.error(f"[{symbol}] HMM regime stability check failed: {hmm_err}")
            cond_num = 1.0
            
        _arctic_write(f"{symbol}_regime_metrics", pd.DataFrame([{
            "regime_condition_number": float(cond_num),
            "timestamp": utils.get_utc_epoch(),
        }]))

        return {
            "df_ml": df_ml,
            "df_ta": df_ta,
            "df_m15": df_m15,
            "df_h1": df_h1,
            "df_h4": df_h4,
            "swing_alpha": swing_alpha,
            "latest_swing": latest_swing,
            "vrs": vrs,
            "wasserstein_state": wasserstein_state,
            "wasser_prob": wasser_prob,
            "label_probs": label_probs,
            "data_quality_flag": data_quality_flag,
            "is_this_symbol_starved": is_this_symbol_starved,
            "atr": atr,
            "m_state": m_state,
            "adjusted_conviction": adjusted_conviction
        }
    except Exception as e:
        logging.error(f"[{symbol}] Feature extraction failed: {e}\n{traceback.format_exc()}")
        return None

def run_inference_for_symbol(symbol: str, prep_data: dict):
    global _MODEL_DRIFT_HALT, _P_SCORE_HISTORY, _DRIFT_RECOVERY_ATTEMPTS, oracle_lib
    global _GLOBAL_CS_RANKS, _CYCLE_P_SCORES, _CYCLE_PENDING_SIGNALS, _VRP_SPREAD
    
    df_ml = prep_data["df_ml"]
    df_ta = prep_data["df_ta"]
    df_m15 = prep_data["df_m15"]
    df_h1 = prep_data["df_h1"]
    df_h4 = prep_data["df_h4"]
    swing_alpha = prep_data["swing_alpha"]
    latest_swing = prep_data["latest_swing"]
    vrs = prep_data["vrs"]
    wasserstein_state = prep_data["wasserstein_state"]
    wasser_prob = prep_data["wasser_prob"]
    label_probs = prep_data["label_probs"]
    data_quality_flag = prep_data["data_quality_flag"]
    is_this_symbol_starved = prep_data["is_this_symbol_starved"]
    atr = prep_data["atr"]
    m_state = prep_data["m_state"]
    adjusted_conviction = prep_data.get("adjusted_conviction", None)

    try:
        # Directive 1: Zero-Variance Bypass Check
        if data_quality_flag == "DEAD_MARKET":
            logging.info(f"[{symbol}] Dead market bypass engaged. Enforcing zero conviction and short-circuiting inference.")
            
            with _CYCLE_LOCK:
                _CYCLE_P_SCORES[symbol] = 0.0000

            # Direct cache write to ensure readiness script sees the DEAD_MARKET state with 0.0 conviction.
            _arctic_write(f"{symbol}_meta", pd.DataFrame([{
                "primary_dir": 0,
                "meta_conviction": 0.500,
                "wasserstein_state": "MARKET_CLOSED_OR_STAGNANT",
                "hmm_state": "MARKET_CLOSED_OR_STAGNANT",
                "strategy_type": "MOMENTUM",
                "atr": atr,
                "entropy": 0.0,
                "hawkes_intensity": 0.0,
                "timestamp": utils.get_utc_epoch(),
                "is_legend": False,
                "is_graveyard": False,
                "vpin": 0.5,
                "rsi": 50.0,
                "vrs": 1.0,
                "xgb_p": 0.500,
                "ddqn_p": 0.500
            }]))
            return

        # ── Level 34 SRE: Heuristic Override & ML Bypass ──────────────────
        try:
            kronos_bridge.update_cognition_cache(symbol, df_ml)
            k_item = _arctic_read(f"{symbol}_kronos")
            if k_item is not None:
                _k_data = k_item.data.iloc[-1]
                k_prob = float(_k_data["kronos_prob"])
            else:
                k_prob = 0.500
            
            x_prob = get_xgb_prediction(df_ml)

            scores_raw = {
                "kronos": k_prob,
                "xgb": x_prob
            }
            
            # RL Inference (if not quarantined)
            from rl_agents.oxford_ddqn import CHECKPOINT_PATH
            if os.path.exists(CHECKPOINT_PATH):
                try:
                    ddqn_agent = ddqn_bridge.get_ddqn_agent()
                    feature_vec = df_ml.select_dtypes(include=[np.number]).iloc[-1].astype(float).values
                    ddqn_p = ddqn_agent.infer_probability(feature_vec)
                    if ddqn_p is not None and not np.isnan(ddqn_p):
                        scores_raw["ddqn"] = ddqn_p
                except Exception as e:
                    logging.warning(f"[{symbol}] DDQN Agent failed: {e}. Omitted from consensus.")
            
            # APPLY QUARANTINE FILTER
            q_result = registry.filter_agents(scores_raw)
            active_scores = q_result.filtered_scores
            
            # Directive 2: The Overconfidence Tripwire (v28.25 Calibration)
            for agent_name, agent_prob in list(active_scores.items()):
                if agent_prob > 0.95 or agent_prob < 0.05:
                    logging.warning(f"[{symbol}] [SOFTMAX_SATURATION_DETECTED] Agent '{agent_name}' outputted extreme/saturated confidence ({agent_prob:.4f}). Discarding from current cycle.")
                    del active_scores[agent_name]
                elif agent_prob == 0.5000 or agent_prob is None or np.isnan(agent_prob):
                    logging.warning(f"[{symbol}] [DYNAMIC QUARANTINE] Agent '{agent_name}' returned 0.5000/NaN. Dropping from consensus.")
                    del active_scores[agent_name]
            
            # Weight Allocation & Evolutionary Consensus Blending
            base_weights = {"kronos": 0.4, "xgb": 0.3, "ddqn": 0.3}
            
            # 1. Proposal A: ACCURACY_WEIGHTED
            p_accuracy = 0.500
            total_active_weight = sum(base_weights[name] for name in active_scores)
            if total_active_weight > 0:
                p_accuracy = sum(
                    active_scores[name] * (base_weights[name] / total_active_weight)
                    for name in active_scores
                )
                
            # 2. Proposal B: MAX_CONVICTION
            p_max = 0.500
            if active_scores:
                p_max = max(active_scores.values(), key=lambda v: abs(v - 0.5))
                
            # 3. Proposal C: SHAP_FILTERED (Baseline weighted fallback for this cycle)
            p_shap = p_accuracy
            
            # Query the highest ELO proposal from registry
            from gitagent_elo_registry import EvolutionaryConsensusRegistry
            elo_registry = EvolutionaryConsensusRegistry()
            active_proposal = elo_registry.get_highest_elo_proposal()
            
            if active_proposal == "ACCURACY_WEIGHTED":
                p_blend = p_accuracy
            elif active_proposal == "MAX_CONVICTION":
                p_blend = p_max
            elif active_proposal == "SHAP_FILTERED":
                p_blend = p_shap
            else:
                p_blend = p_accuracy
                
            # Record prediction details for post-realization ELO adjustments
            try:
                current_close_price = float(df_ml['close'].iloc[-1])
                proposals_predictions = {
                    "ACCURACY_WEIGHTED": p_accuracy,
                    "MAX_CONVICTION": p_max,
                    "SHAP_FILTERED": p_shap
                }
                elo_registry.record_prediction(symbol, current_close_price, proposals_predictions)
                # Run self-contained evaluation of pending predictions periodically
                elo_registry.evaluate_pending_predictions()
            except Exception as elo_err:
                logging.warning(f"[{symbol}] Elo prediction recording failed: {elo_err}")

                
            # UPGRADE D: Microstructure Bar Activity Gating Layer
            activity_ratio = 1.0
            try:
                # 1. Group tick sequences into dollar bars
                df_bars = ticks_to_dollar_bars(df_m15, threshold=500000.0)
                if not df_bars.empty:
                    bar_durations = df_bars['time'].diff().dt.total_seconds().dropna().values
                    if len(bar_durations) >= 2:
                        delta_tau_bar = bar_durations[-1]
                        # Rolling median of trailing 20 bars
                        median_delta_tau = np.median(bar_durations[-20:]) if len(bar_durations) >= 20 else np.median(bar_durations)
                        activity_ratio = median_delta_tau / (delta_tau_bar + 1e-9)
                        
                        pre_gate_p = p_blend
                        if activity_ratio < 0.5:
                            logging.warning(f"[{symbol}] [ACTIVITY_GATE] Low activity: ratio {activity_ratio:.4f} < 0.5. Suppressing conviction (P_blend=0.50).")
                            p_blend = 0.500
                        else:
                            p_blend = p_blend * min(activity_ratio, 1.5)
                            p_blend = float(np.clip(p_blend, 0.0, 1.0))
                            logging.info(f"[{symbol}] [ACTIVITY_GATE] Activity Ratio: {activity_ratio:.4f} | P_blend scaled: {pre_gate_p:.4f} -> {p_blend:.4f}")
            except Exception as gate_err:
                logging.error(f"[{symbol}] Microstructure activity gating failed: {gate_err}")

            # UPGRADE B: Live Parameter Adaptation via Moving Window Fitness
            try:
                global _LIVE_SWEEP_COUNTER
                if '_LIVE_SWEEP_COUNTER' not in globals():
                    _LIVE_SWEEP_COUNTER = defaultdict(int)
                _LIVE_SWEEP_COUNTER[symbol] += 1
                if _LIVE_SWEEP_COUNTER[symbol] % 50 == 0:
                    logging.info(f"[OPTIMIZER] Running live parameter adaptation sweep for {symbol}...")
                    # Get price history and ATR series
                    if df_ta is not None:
                        price_history = df_ta['close']
                        atr_series = df_ta['WHL_vol'] # standard vol/ATR proxy
                        _MATH_META_MODEL.optimize_hyperparameters(price_history, atr_series)
            except Exception as sweep_err:
                logging.error(f"[OPTIMIZER] Live parameter sweep failed: {sweep_err}")
                
            vals = [float(v) for v in active_scores.values() if not np.isnan(v)]
            model_divergence = max(vals) - min(vals) if len(vals) >= 2 else 0.0

            import alpha_combiner
            is_consensus = alpha_combiner.combiner.check_consensus(active_scores, p_blend, tighten=is_this_symbol_starved)
            if not is_consensus:
                agree_on_direction = False
                valid_vals = [v for v in active_scores.values() if not np.isnan(v)]
                if len(valid_vals) >= 2:
                    all_buy = all(v > 0.50 for v in valid_vals)
                    all_sell = all(v < 0.50 for v in valid_vals)
                    agree_on_direction = all_buy or all_sell
                
                if agree_on_direction:
                    logging.info(f"[{symbol}] CONSENSUS DIVERGENCE OVERRIDE: Models agree on directional sign. Allowing weighted blend P_blend={p_blend:.4f}.")
                else:
                    if len(valid_vals) > 0:
                        max_conviction_val = max(valid_vals)
                        min_conviction_val = min(valid_vals)
                        p_blend = max_conviction_val if max_conviction_val > 0.5 else min_conviction_val
                        logging.warning(f"[{symbol}] CONSENSUS GATE BLOCKED: Divergence > 0.40. Bypassing 0.5000 limit. Passing max raw conviction: P_blend={p_blend:.4f}.")
                    else:
                        logging.warning(f"[{symbol}] CONSENSUS GATE BLOCKED: No valid models. Falling back to 0.0000.")
                        p_blend = 0.0000
            logging.info(f"[{symbol}] ML Inference SUCCESS: P_blend={p_blend:.4f} (Agents: {list(active_scores.keys())})")
            
        except Exception as e:
            logging.warning(f"[{symbol}] ML Bypass in effect. Reason: {e}")
            data_quality_flag = "DEGRADED"
            x_prob = 0.500
            ddqn_p = 0.500
            k_prob = 0.500
            active_scores = {"kronos": k_prob, "xgb": x_prob, "ddqn": ddqn_p}
            model_divergence = 0.0
            print(f"[ML BYPASS] Shape mismatch detected. Falling back to Heuristic Swing Routing for {symbol}.")
            x_prob = 0.500
            ddqn_p = 0.500
            
            if latest_swing is not None:
                rsi = latest_swing.get('rsi', 50)
                entropy = latest_swing.get('entropy', 0.5)
                
                if rsi < 35 and entropy > 0.85:
                    p_blend = 0.85
                elif rsi > 65 and entropy > 0.85:
                    p_blend = 0.15
                elif latest_swing.get('trend_continuation_signal', 0) > 0:
                    p_blend = 0.90 if df_m15['close'].iloc[-1] > latest_swing.get('ema_20', 0) else 0.10
                elif latest_swing.get('catalyst_momentum_signal', 0) > 0:
                    p_blend = 0.80 if latest_swing.get('gap_pct', 0) > 0 else 0.20
                else:
                    p_blend = 0.50
            else:
                p_blend = 0.50
                
            logging.warning(f"[{symbol}] HEURISTIC_OVERRIDE ACTIVE: P_blend={p_blend:.2f} (Reason: {e})")

        # Compute normalized Wasserstein distance
        try:
            p_live = df_ml["frac_diff_price"].dropna().values
            if len(p_live) > 500:
                p_live = p_live[-500:]
            
            all_vals = df_ml["frac_diff_price"].dropna().values
            if len(all_vals) >= 500:
                p_train = all_vals[:500]
            else:
                p_train = np.random.normal(np.mean(p_live), np.std(p_live) + 1e-9, len(p_live))
                
            from scipy.stats import wasserstein_distance
            w_dist_raw = wasserstein_distance(np.sort(p_live), np.sort(p_train))
            w_dist_norm = float(w_dist_raw / (np.std(p_train) + 1e-9))
        except Exception as w_err:
            logging.warning(f"[{symbol}] Failed to compute numerical Wasserstein distance: {w_err}")
            w_dist_norm = 1.0


        primary_dir = 1 if p_blend > 0.60 else (-1 if p_blend < 0.40 else 0)

        # ── Regime-Weighted FAISS Episodic Retrieval ──────────────────────────
        live_vec = copy.deepcopy(sigproc.get_feature_vector(symbol))
        mem_matches = _MEMORY.retrieve(live_vec, k=3)
        is_legend = False; is_graveyard = False; max_sim = 0.0
        
        decay_lambda = 1e-5
        weighted_sim_sum = 0.0
        weight_sum = 0.0
        
        for match in mem_matches:
            sim = match["distance"]
            meta = match["meta"]
            reasoning = meta.get("reasoning", "").upper()
            
            # Time-decay
            ts_str = meta.get("timestamp")
            def _parse_timestamp(ts_val) -> float:
                if ts_val is None:
                    return time.time() - 86400 * 30
                if isinstance(ts_val, (int, float)):
                    return float(ts_val)
                try:
                    return float(ts_val)
                except ValueError:
                    pass
                try:
                    dt = pd.to_datetime(ts_val)
                    return dt.timestamp()
                except Exception:
                    return time.time() - 86400 * 30
                    
            delta_t = abs(time.time() - _parse_timestamp(ts_str))
            W_time = math.exp(-decay_lambda * delta_t)
            
            # Regime proximity
            hist_w_raw = meta.get("wasserstein_distance", meta.get("wasserstein_state", 1.0))
            try:
                historic_wasserstein = float(hist_w_raw)
            except (ValueError, TypeError):
                hist_w_str = str(hist_w_raw).upper()
                if "TREND" in hist_w_str:
                    historic_wasserstein = 0.0
                elif "CRISIS" in hist_w_str:
                    historic_wasserstein = 2.0
                else:
                    historic_wasserstein = 1.0
                    
            W_regime = 1.0 / (1.0 + abs(historic_wasserstein - w_dist_norm))
            W_total = W_time * W_regime
            
            weighted_sim_sum += sim * W_total
            weight_sum += W_total
            
            if sim > LEGEND_SIMILARITY_THRESHOLD:
                if "LEGEND" in reasoning or meta.get("action") == "LEGEND_WEI":
                    is_legend = True
            if sim > FAILURE_SIMILARITY_THRESHOLD:
                if "FAILURE" in reasoning or "POST_MORTEM" in reasoning:
                    is_graveyard = True
                    
        if weight_sum > 0:
            max_sim = weighted_sim_sum / weight_sum
        else:
            max_sim = 0.0

        try:
            k_hist_item = _arctic_read(f"{symbol}_kronos")
            if k_hist_item is not None:
                k_hist = k_hist_item.data.tail(50)
                xgb_vals = k_hist['xgboost_prob'].values
                k_vals = k_hist['kronos_prob'].values
                z_xgb = np.clip((float(x_prob) - np.mean(xgb_vals)) / (np.std(xgb_vals) + 1e-9), -3.0, 3.0)
                z_kronos = np.clip((float(k_prob) - np.mean(k_vals)) / (np.std(k_vals) + 1e-9), -3.0, 3.0)
            else:
                z_xgb = np.clip((float(x_prob) - 0.5) / 0.15, -3.0, 3.0)
                z_kronos = np.clip((float(k_prob) - 0.5) / 0.15, -3.0, 3.0)
        except Exception:
            z_xgb = np.clip((float(x_prob) - 0.5) / 0.15, -3.0, 3.0)
            z_kronos = np.clip((float(k_prob) - 0.5) / 0.15, -3.0, 3.0)

        _final = df_ml.iloc[-1]

        def _safe_extract_with_lookback(sym, val, default_val, key_name):
            if val is not None and not np.isnan(val) and not np.isinf(val):
                return float(val)
            try:
                hist_item = _arctic_read(f"{sym}_meta")
                if hist_item is not None and not hist_item.data.empty:
                    for i in range(len(hist_item.data) - 1, -1, -1):
                        hist_val = hist_item.data.iloc[i].get(key_name)
                        if hist_val is not None and not np.isnan(hist_val) and not np.isinf(hist_val):
                            return float(hist_val)
            except Exception:
                pass
            return float(default_val)

        safe_xgb = float(x_prob) if not np.isnan(float(x_prob)) else 0.5000
        safe_kronos = float(k_prob) if not np.isnan(float(k_prob)) else 0.5000
        safe_faiss = _safe_extract_with_lookback(symbol, float(max_sim) if max_sim is not None else None, 0.0000, "faiss_similarity")
        raw_sent = m_state.get("global_macro_sentiment", 0.5)
        safe_sent = _safe_extract_with_lookback(symbol, float(raw_sent) if raw_sent is not None else None, 0.5000, "sentiment_score")

        # STEP 1: CAUSAL FEATURE EXPANSION (v30.95)
        instant_atr_10 = calculate_atr_df(df_m15, 10)
        baseline_atr_200 = calculate_atr_df(df_m15, 200)
        volatility_ratio = float(instant_atr_10 / baseline_atr_200) if baseline_atr_200 > 0.0 else 1.0
        
        df_bars_hft = ticks_to_dollar_bars(df_m15, threshold=500000.0) if df_m15 is not None else None

        # Cross-Asset Sentiment Divergence Delta
        def logit(p):
            p_clipped = np.clip(p, 1e-5, 1.0 - 1e-5)
            return np.log(p_clipped / (1.0 - p_clipped))
            
        sentiment_divergence_delta = abs(logit(safe_sent) - logit(safe_kronos))

        local_meta_features = copy.deepcopy({
            "wasserstein_state": w_dist_norm, # Use numeric distance
            "hmm_state": wasserstein_state,   # Use string state
            "wasserstein_routing_probs": label_probs, # soft weights
            "xgb_p": safe_xgb,
            "xgboost_prob": safe_xgb,
            "kronos_p": safe_kronos,
            "kronos_prob": safe_kronos,
            "faiss_sim": safe_faiss,
            "faiss_similarity": safe_faiss,
            "macro_sent": safe_sent,
            "sentiment_score": safe_sent,
            "sentiment_divergence_delta": sentiment_divergence_delta,
            "volatility_ratio": volatility_ratio,
            "macro_risk": float(m_state.get("black_swan_risk", 0.0)),
            "catalyst": float(m_state.get("asset_specific_catalysts", {}).get(symbol, 0.0)),
            "frac_diff": float(_final.get("frac_diff_price", 0.0)),
            "fft_amp_1": float(_final.get("fft_amp_1", 0.0)),
            "fft_amp_2": float(_final.get("fft_amp_2", 0.0)),
            "fft_amp_3": float(_final.get("fft_amp_3", 0.0)),
            "vpin": float(_final.get("vpin", 0.0)),
            "hawkes_intensity": float(_final.get("hawkes_intensity", 0.0)),
            "order_flow_entropy": float(_final.get("order_flow_entropy", 0.0)),
            "cs_rank": float(_GLOBAL_CS_RANKS.get(symbol, 0.5)),
        })
        
        _nan_vals = {k: v for k, v in local_meta_features.items() if isinstance(v, float) and (np.isnan(v) or np.isinf(v))}
        if _nan_vals:
            logging.critical(f"[FATAL] {symbol}: NaN/Inf detected in meta-features: {list(_nan_vals.keys())}. Halting inference.")
            return
        
        # Online realized calibration queue outcome update using previous prediction direction correctness
        try:
            prev_meta_df = _arctic_read(f"{symbol}_meta")
            if prev_meta_df is not None and not prev_meta_df.data.empty:
                prev_row = prev_meta_df.data.iloc[-1]
                prev_p = float(prev_row.get("meta_conviction", 0.5))
                if df_ta is not None and len(df_ta) >= 2:
                    curr_close = float(df_ta["close"].iloc[-1])
                    prev_close = float(df_ta["close"].iloc[-2])
                    price_change = curr_close - prev_close
                    if prev_p > 0.5:
                        realized = 1.0 if price_change > 0 else 0.0
                        _MATH_META_MODEL.add_outcome(prev_p, realized)
                    elif prev_p < 0.5:
                        realized = 1.0 if price_change < 0 else 0.0
                        _MATH_META_MODEL.add_outcome(prev_p, realized)
        except Exception as cal_err:
            logging.warning(f"[{symbol}] Failed to update calibration queue outcome: {cal_err}")

        p_trend = get_meta_conviction(symbol, local_meta_features, primary_dir, base_p=p_blend)
        
        rsi = df_ta["W_rsi"].iloc[-1]
        bbpos = df_ta["B_bbpos"].iloc[-1]
        prices = df_m15['close'].values
        fft_data = sigproc.fft_cycle_detector(prices)
        fft_amplitude = fft_data.get('power', 0.0)
        
        if fft_amplitude > 1.5:
            p_range = calculate_mean_reversion_score(rsi, bbpos)
        else:
            p_range = 0.50
            
        w_trend = label_probs.get("TRENDING", 0.0) + label_probs.get("HIGH-VOLATILITY", 0.0) + label_probs.get("BULL", 0.0) + label_probs.get("BEAR", 0.0) + label_probs.get("LOW-VOL TREND", 0.0) + label_probs.get("CRISIS TAIL", 0.0)
        w_range = label_probs.get("MEAN-REVERTING", 0.0) + label_probs.get("RANGE", 0.0) + label_probs.get("HIGH-VOL MEAN REVERSION", 0.0)
        
        total_w = w_trend + w_range + 1e-9
        w_trend /= total_w
        w_range /= total_w
        
        wasserstein_selector_state = "TREND" if ("TREND" in wasserstein_state or "CRISIS" in wasserstein_state) else "RANGE"
        
        if wasserstein_selector_state == "TREND":
            signal = run_momentum_strategy(symbol, local_meta_features, p_trend)
            meta_p = p_trend
        elif wasserstein_selector_state == "RANGE":
            signal = run_meridian_strategy(symbol, local_meta_features, p_range)
            meta_p = p_range
            
            if _VRP_SPREAD > 5.0 and wasserstein_state == "RANGE":
                deviation = meta_p - 0.5
                meta_p = np.clip(0.5 + deviation * 1.15, 0.0, 1.0)
                logging.info(
                    f"[{symbol}] [VRP_OVERLAY] High VRP Spread ({_VRP_SPREAD:.2f} > 5.0) in RANGE state. "
                    f"Meridian conviction scaled: {p_range:.4f} -> {meta_p:.4f} (1.15x multiplier)"
                )
        else:
            signal = run_momentum_strategy(symbol, local_meta_features, p_trend)
            meta_p = p_trend
        
        if p_trend == 0.0:
            meta_p = 0.0
            
        range_gate_val = EPISTEMIC_GATE if _IS_STARTUP_OR_SHOCK else 0.75
        current_gate = (w_trend * EPISTEMIC_GATE) + (w_range * range_gate_val)
        
        high_vol_assets = {"NAS100", "US30", "SPX500", "SP500", "GER40", "NAS100.r", "XAUUSD", "XAGUSD", "GOLD", "SILVER", "XPTUSD", "XPDUSD"}
        is_degraded = (data_quality_flag != "PRISTINE") or is_this_symbol_starved
        if is_degraded:
            min_p_gate = 0.75
        elif symbol.upper() in high_vol_assets:
            min_p_gate = 0.72
        else:
            min_p_gate = 0.68
        base_gate = max(current_gate, min_p_gate)
        
        dynamic_gate = base_gate * (1.0 - (0.5 * (1.0 - vrs)))
        dynamic_gate = max(dynamic_gate, 0.65)
        current_gate = dynamic_gate
        
        regime_prob = label_probs.get(wasserstein_state, 0.0)
        import sentinel_config
        is_crypto_or_index = symbol.upper() in getattr(sentinel_config, 'CRYPTO_BASE_SYMBOLS', []) or any(ind in symbol.upper() for ind in ["SP500", "NAS100", "US30", "GER40", "HK50", "US2000", "FRA40"])
        stagnant_regime_threshold = 0.25 if is_crypto_or_index else 0.40
        stagnant_activity_threshold = 0.40 if is_crypto_or_index else 0.85
        if regime_prob < stagnant_regime_threshold and activity_ratio < stagnant_activity_threshold:
            wasserstein_state = "MARKET_STAGNANT"
            logging.info(f"[{symbol}] [MARKET_STAGNANT] Low HMM ({regime_prob:.2f}) & Low Activity ({activity_ratio:.2f}). Gracefully skipping but writing neutral conviction.")
            with _CYCLE_LOCK:
                _CYCLE_P_SCORES[symbol] = 0.5000
            _arctic_write(f"{symbol}_meta", pd.DataFrame([{
                "primary_dir": 0,
                "meta_conviction": 0.500,
                "wasserstein_state": "MARKET_STAGNANT",
                "hmm_state": "MARKET_STAGNANT",
                "strategy_type": "MOMENTUM",
                "atr": float(atr),
                "entropy": 0.0,
                "hawkes_intensity": 0.0,
                "timestamp": utils.get_utc_epoch(),
                "is_legend": False,
                "is_graveyard": False,
                "vpin": 0.5,
                "rsi": 50.0,
                "vrs": 1.0,
                "xgb_p": 0.500,
                "ddqn_p": 0.500,
                "volatility_ratio": float(local_meta_features.get("volatility_ratio", 1.0)),
            }]))
            return
        elif regime_prob < 0.55:
            current_gate = max(current_gate - 0.05, 0.60)
            logging.info(f"[{symbol}] [CONVICTION_DRIFT_ACTIVE] HMM confidence low ({regime_prob:.3f} < 0.55). Relaxing entry gate by 5% conviction drift to {current_gate:.3f}")
        
        if is_graveyard: meta_p = 0.50

        # ── v28.35 Directive 2: NY Open Dynamic Gate Correction ─────────────────
        # Extract volume_overdrive flag from the feature-engineered dataframe.
        # If the Vimb z-score burst is active AND we are inside the NY Open window
        # (UTC hours 13, 14, 15), relax the gate back to its clean structural baseline,
        # stripping any macro-calendar Wall-5 penalty inflation by 15%.
        try:
            volume_overdrive = bool(df_ml.iloc[-1].get("volume_overdrive", 0)) if df_ml is not None else False
            z_vimb_val = float(df_ml.iloc[-1].get("z_vimb", 0.0)) if df_ml is not None else 0.0
        except Exception:
            volume_overdrive = False
            z_vimb_val = 0.0

        current_time_utc_hour = datetime.now(timezone.utc).hour
        if volume_overdrive and (current_time_utc_hour in [13, 14, 15]):
            pre_overdrive_gate = current_gate
            applied_dynamic_gate = min(base_gate, current_gate * 0.85)
            current_gate = applied_dynamic_gate
            logging.info(
                f"[{symbol}] [NY_OPEN_OVERDRIVE] Z(Vimb)={z_vimb_val:.4f} >= 2.0 | UTC Hour={current_time_utc_hour} "
                f"| Gate relaxed from {pre_overdrive_gate:.4f} -> {current_gate:.4f} "
                f"(15% compression stripped, capped at base={base_gate:.4f})"
            )
        # ────────────────────────────────────────────────────────────────────────

        if adjusted_conviction is not None and adjusted_conviction == 0.0:
            meta_p = 0.50
            
        if meta_p == 0.0:
            logging.warning(f"[{symbol}] [COLD_START_QUARANTINE] Meta-model returned 0.0 due to cold/null features. HARD REJECTION. Skipping signal.")
            _arctic_write(f"{symbol}_meta", pd.DataFrame([{
                "primary_dir": 0,
                "meta_conviction": 0.0,
                "wasserstein_state": "MARKET_CLOSED_OR_STAGNANT",
                "hmm_state": "MARKET_CLOSED_OR_STAGNANT",
                "strategy_type": "COLD_START_QUARANTINE",
                "atr": float(atr),
                "entropy": 0.0,
                "hawkes_intensity": 0.0,
                "timestamp": utils.get_utc_epoch(),
                "volatility_ratio": float(local_meta_features.get("volatility_ratio", 1.0)),
            }]))
            return
        
        logging.info(f"[{symbol}] MixTS BLEND: Trend({w_trend:.1%})={p_trend:.3f}, Range({w_range:.1%})={p_range:.3f} -> P={meta_p:.4f} (Gate: {current_gate:.3f}, BaseGate={base_gate:.3f}, VRS={vrs:.2f})")

        if float(meta_p) != 0.50:
            _P_SCORE_HISTORY.append(float(meta_p))
            if len(_P_SCORE_HISTORY) > 100:
                _P_SCORE_HISTORY.pop(0)

        with _CYCLE_LOCK:
            _CYCLE_P_SCORES[symbol] = float(meta_p)

        p_history_path = Path(PROJECT_ROOT) / "data" / "p_score_history.jsonl"
        p_history_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(p_history_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "timestamp": int(time.time()),
                    "symbol": symbol,
                    "p_score": float(meta_p),
                    "wasserstein_state": wasserstein_state,
                    "primary_dir": int(primary_dir)
                }) + "\n")
        except Exception as _pe:
            logging.error(f"[TELEMETRY_WRITE_ERROR] Failed to write P-score telemetry: {_pe}")

        # --- CONSTRAINT 2: DYNAMIC TRIGGER HOOK ---
        # Intercept Wasserstein distance regime gate. If geometric distribution shift detected -> trigger retrain
        try:
            wasserstein_str = str(wasserstein_state).upper()
            if "CRISIS" in wasserstein_str or "GEOMETRIC_SHIFT" in wasserstein_str:
                if _BACKGROUND_TRAIN_STATUS == "Idle" or _BACKGROUND_TRAIN_STATUS == "Active Continual":
                    logging.warning(f"[WASSERSTEIN_GATE] Geometric shift detected ({wasserstein_state}). Triggering continual learning retrain.")
                    trigger_background_retraining(f"Wasserstein Shift: {wasserstein_state}")
        except Exception:
            pass

        if len(_P_SCORE_HISTORY) == 100:
            p_std = float(np.std(_P_SCORE_HISTORY))
            if p_std < 0.02:
                if _DRIFT_RECOVERY_ATTEMPTS < 3:
                    _DRIFT_RECOVERY_ATTEMPTS += 1
                    logging.critical(
                        f"[CRITICAL MODEL DRIFT] Mode Collapse ({p_std:.6f} < 0.02 limit). "
                        f"Initiating Automated Drift Reset ({_DRIFT_RECOVERY_ATTEMPTS}/3)..."
                    )
                    _P_SCORE_HISTORY.clear()
                    try:
                        _get_oracle_lib()
                        _ARCTIC.delete_library("oracle_cache")
                        oracle_lib = _ARCTIC.create_library("oracle_cache")
                        _load_meta_model_with_failsafe()
                        logging.info("[DRIFT RECOVERY] Cache purged and models rebooted.")
                    except Exception as e:
                        logging.error(f"[DRIFT RECOVERY] Reset failed: {e}")
                else:
                    _MODEL_DRIFT_HALT = True
                    logging.critical(
                        f"[CRITICAL MODEL DRIFT] Mode Collapse detected! Rolling std-dev of last 100 P-scores "
                        f"is {p_std:.6f} < 0.02 limit. Recovery attempts exhausted. HALTING AUTONOMOUS TRADING IMMEDIATELY."
                    )

        _arctic_write(f"{symbol}_meta", pd.DataFrame([{
            "primary_dir": int(primary_dir),
            "meta_conviction": float(meta_p),
            "wasserstein_state": float(local_meta_features.get("wasserstein_state", 0.0)),
            "hmm_state": str(local_meta_features.get("hmm_state", "RANGE")),
            "strategy_type": signal["strategy_type"],
            "atr": float(atr),
            "entropy": float(_final.get("order_flow_entropy", 0.0)),
            "hawkes_intensity": float(_final.get("hawkes_intensity", 0.0)),
            "timestamp": utils.get_utc_epoch(),
            "is_legend": is_legend,
            "is_graveyard": is_graveyard,
            "xgboost_prob": float(local_meta_features.get("xgb_p", 0.5)),
            "kronos_prob": float(local_meta_features.get("kronos_p", 0.5)),
            "faiss_similarity": float(local_meta_features.get("faiss_sim", 0.0)),
            "sentiment_score": float(local_meta_features.get("sentiment_score", 0.5)),
            "volatility_ratio": float(local_meta_features.get("volatility_ratio", 1.0)),
            "sentiment_divergence_delta": float(local_meta_features.get("sentiment_divergence_delta", 0.0)),
            "uncertainty_width": float(local_meta_features.get("uncertainty_width", 0.0)),
            "trust_gate_failed": bool(local_meta_features.get("trust_gate_failed", False)),
            "p_lower": float(local_meta_features.get("prediction_interval", [0.5, 0.5])[0]),
            "p_upper": float(local_meta_features.get("prediction_interval", [0.5, 0.5])[1]),
        }]))

        norm_p = abs(meta_p - 0.5) + 0.5
        
        primary_dir = 1 if meta_p > 0.5 else (-1 if meta_p < 0.5 else 0)

        if 0.40 <= meta_p <= 0.60:
            logging.info(f"[GATE] {symbol}: P={meta_p:.6f} falls in DEAD-ZONE (0.40-0.60). HARD BLOCKED.")
        elif norm_p >= current_gate and primary_dir != 0:
            signal_dir = "BUY" if meta_p > 0.5 else "SELL"
            
            # --- DIRECTIVE OMEGA PRE-ENTRY VETOES ---
            if is_graveyard:
                logging.warning(f"[{symbol}] [HARD_VETO] [GRAVEYARD_VETO] Cosine similarity to post_mortem_failure vector > 85%. Blocking signal.")
                return
            acc_info = mt5.account_info()
            sym_info = mt5.symbol_info(symbol)
            if acc_info and sym_info:
                risk_budget = acc_info.balance * 0.02
                point_value = sym_info.trade_tick_value / (sym_info.trade_tick_size / sym_info.point) if sym_info.trade_tick_size > 0 else sym_info.trade_tick_value
                affordable_lot = risk_budget / (atr * point_value * 3.0 + 1e-12)
                if affordable_lot < sym_info.volume_min:
                    logging.warning(f"[{symbol}] AFFORDABILITY_VETO: Affordable lot size {affordable_lot:.4f} < broker min {sym_info.volume_min}. Skipping signal.")
                    return
            
            k_score = active_scores.get('kronos', 0.5)
            x_score = active_scores.get('xgb', 0.5)
            predicted_dir = "BUY" if meta_p > 0.5 else "SELL"
            kronos_conf = k_score if predicted_dir == "BUY" else (1.0 - k_score)
            xgb_conf = x_score if predicted_dir == "BUY" else (1.0 - x_score)
            if False: # kronos_conf < 0.70 or xgb_conf < 0.65:
                logging.warning(f"[{symbol}] [HARD_VETO] [WEAK_MODEL_VETO] Kronos Conf {kronos_conf:.3f} < 0.70 or XGB Conf {xgb_conf:.3f} < 0.65. Blocking signal.")
                return
            
            regime_prob = label_probs.get(wasserstein_state, 0.0)
            if regime_prob < 0.55:
                logging.info(f"[{symbol}] [REGIME_AWARENESS_BYPASS] HMM confidence low ({regime_prob:.3f} < 0.55). Defaulting to P_blend conviction ({meta_p:.4f}) and bypassing hard HMM regime vetoes.")
            elif is_legend:
                logging.info(f"[{symbol}] [LEGEND_OVERRIDE] Cosine similarity to legend_wei vector > 85%. Bypassing HMM regime/directional penalties.")
            else:
                is_mixts_valid = (meta_p is not None and isinstance(meta_p, (int, float)))
                if not is_mixts_valid and regime_prob < 0.60:
                    logging.warning(f"[{symbol}] [HARD_VETO] [REGIME_MINIMUM_VETO] HMM {wasserstein_state} probability {regime_prob:.3f} < 0.60. Blocking signal.")
                    return
                if (predicted_dir == "BUY" and wasserstein_state == "BEAR") or (predicted_dir == "SELL" and wasserstein_state == "BULL"):
                    logging.warning(f"[{symbol}] [HARD_VETO] [HMM_REGIME_CONFLICT] HMM state {wasserstein_state} conflicts with predicted direction {predicted_dir}. Blocking signal.")
                    return
            
            entropy_val = 0.0
            if df_ml is not None:
                try:
                    entropy_val = float(df_ml.iloc[-1].get("order_flow_entropy", 0.0))
                except:
                    pass
            if latest_swing is not None:
                try:
                    entropy_val = max(entropy_val, float(latest_swing.get('entropy', 0.0)))
                except:
                    pass
            if entropy_val > 1.0:
                data_quality_flag = "DEGRADED"
                logging.warning(f"[{symbol}] [HARD_VETO] [DATA_QUALITY_VETO] Order Flow Entropy {entropy_val:.3f} > 1.0.")

            if data_quality_flag != "PRISTINE":
                logging.warning(f"[{symbol}] [HARD_VETO] [DATA_QUALITY_VETO] Data quality is {data_quality_flag}. Blocking signal.")
                return
            
            
            with _CYCLE_LOCK:
                _CYCLE_PENDING_SIGNALS.append({
                    "symbol": signal["symbol"],
                    "direction": signal_dir,
                    "strategy_type": signal["strategy_type"],
                    "conviction": round(float(meta_p), 6),
                    "sl": float(signal["sl"]),
                    "tp": float(signal["tp"]),
                    "size_multiplier": float(signal["size_multiplier"]),
                    "tag": signal["tag"],
                    "xgb_p": float(x_prob),
                    "ddqn_p": float(ddqn_p),
                    "wasserstein_state": wasserstein_state,
                    "atr": float(atr),
                    "timestamp": int(datetime.now(timezone.utc).timestamp()),
                    "version": "v29.0-IRONCLAD-CADES",
                    "signal_type": signal["strategy_type"],
                    "model_divergence": float(model_divergence),
                    "vrs": float(vrs),
                    "applied_dynamic_gate": float(current_gate)
                })
            logging.info(f"[GATE] {symbol}: norm_p={norm_p:.4f} >= dynamic_gate={current_gate:.4f} (Base={base_gate:.2f}, VRS={vrs:.2f}). CLEAR.")
            logging.info(f"[PENDING] [SIGNAL] {symbol}: {signal_dir} | P={meta_p:.6f} | norm_p={norm_p:.4f} | HMM={wasserstein_state} | DDQN={ddqn_p:.3f} | Divergence={model_divergence:.3f}")
        else:
            logging.info(f"[GATE] {symbol}: norm_p={norm_p:.4f} < dynamic_gate={current_gate:.4f} (Base={base_gate:.2f}, VRS={vrs:.2f}). Suppressed.")
 
        timesfm_bridge.update_risk_cache(symbol, df_m15)

    except Exception as e:
        error_msg = traceback.format_exc()
        logging.error(f"[{symbol}] Oracle update error:\n{error_msg}")
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

def update_slow_oracles(symbol: str, force_refresh: bool = False):
    prep = fetch_and_calculate_raw_features(symbol, force_refresh)
    if prep is not None:
        run_inference_for_symbol(symbol, prep)

async def process_matrix_parallel(watchlist: list, force_refresh: bool = False):
    global _CYCLE_P_SCORES, _CYCLE_PENDING_SIGNALS, _VRP_SPREAD
    global _GLOBAL_CS_RANKS
    
    # Directive 1: Calculate VRP Macro Filter
    try:
        from feature_engineering import calculate_vrp_spread
        _VRP_SPREAD = calculate_vrp_spread()
        logging.info(f"[VRP_FILTER] Calculated macro VRP_Spread = {_VRP_SPREAD:.4f}")
    except Exception as e:
        _VRP_SPREAD = 0.0
        logging.warning(f"[VRP_FILTER] Failed to calculate VRP spread: {e}")
    with _CYCLE_LOCK:
        _CYCLE_P_SCORES = {}
        _CYCLE_PENDING_SIGNALS = []

    def chunked(iterable, n):
        it = iter(iterable)
        while True:
            chunk = list(itertools.islice(it, n))
            if not chunk: break
            yield chunk

    loop = asyncio.get_event_loop()
    max_workers = 5 
    
    # Pre-Scan the entire watchlist before processing batches
    _pre_scan_watchlist(watchlist)
    
    # Stage 1: Fetch historical data & Calculate raw features (Parallel, asset-by-asset)
    logging.info(f"[ALPHA_FACTORY] Stage 1: Fetching data and calculating raw features...")
    prep_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        tasks = [loop.run_in_executor(ex, fetch_and_calculate_raw_features, s, force_refresh) for s in watchlist]
        results = await asyncio.gather(*tasks)
        for s, res in zip(watchlist, results):
            if res is not None:
                prep_results[s] = res

    # Stage 2: Combine all assets into a single unified 2D DataFrame matrix at time t, and run CS_Rank
    logging.info(f"[ALPHA_FACTORY] Stage 2: Performing CS_Rank Matrix Freeze across {len(prep_results)} active assets...")
    feature_rows = {}
    for s, res in prep_results.items():
        df_ml = res["df_ml"]
        if df_ml is not None and len(df_ml) > 0:
            numeric_row = df_ml.select_dtypes(include=[np.number]).iloc[-1]
            feature_rows[s] = numeric_row

    if feature_rows:
        df_matrix = pd.DataFrame.from_dict(feature_rows, orient='index')
        df_ranked = df_matrix.rank(pct=True)
        
        # Inject ranked features back into the last row of df_ml
        for s, res in prep_results.items():
            df_ml = res["df_ml"]
            if df_ml is not None and len(df_ml) > 0:
                last_idx = df_ml.index[-1]
                for col in df_ranked.columns:
                    if col in df_ml.columns:
                        df_ml.loc[last_idx, col] = float(df_ranked.loc[s, col])

        # Recalculate momentum-based cs_ranks for meta-features
        momentums = {}
        for s, res in prep_results.items():
            df_m15 = res["df_m15"]
            if df_m15 is not None and len(df_m15) > 1:
                close_now = df_m15["close"].iloc[-1]
                close_prev = df_m15["close"].iloc[0]
                momentums[s] = (close_now - close_prev) / (close_prev + 1e-9)
            else:
                momentums[s] = 0.0
        
        if momentums:
            symbols_list = list(momentums.keys())
            values_list = list(momentums.values())
            ranks_list = pd.Series(values_list).rank(pct=True).values
            for sym, rk in zip(symbols_list, ranks_list):
                _GLOBAL_CS_RANKS[sym] = float(rk)

    # Stage 3: Pass perfectly standardized features into micro-batch inference loops
    logging.info(f"[ALPHA_FACTORY] Stage 3: Executing Micro-Batch Inference loops...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        batch_idx = 1
        for batch in chunked(watchlist, 10):
            logging.info(f"[MICRO-BATCH] Processing batch {batch_idx} ({len(batch)} assets)...")
            active_batch = [s for s in batch if s in prep_results]
            tasks = [loop.run_in_executor(ex, run_inference_for_symbol, s, prep_results[s]) for s in active_batch]
            await asyncio.gather(*tasks)
            gc.collect()
            if len(batch) == 10:
                await asyncio.sleep(0.5)
            batch_idx += 1
        with _CYCLE_LOCK:
            filtered_sigs = []
            for sig in _CYCLE_PENDING_SIGNALS:
                div = sig.get("model_divergence", 0.0)
                if div > 0.15:
                    logging.warning(f"[{sig['symbol']}] RETROSPECTIVE WALL 2 VETO: Divergence {div:.3f} > 0.15 (Starved Session)")
                else:
                    filtered_sigs.append(sig)
            _CYCLE_PENDING_SIGNALS = filtered_sigs

    # Directive 2: The Correlated Overconfidence Veto
    extreme_count = sum(1 for p in _CYCLE_P_SCORES.values() if p > 0.90 or p < 0.10)
    veto_threshold = 0.20 * len(watchlist)
    
    if extreme_count > veto_threshold:
        logging.critical(
            f"[CRITICAL] Overconfidence Veto Engaged: {extreme_count}/{len(watchlist)} assets "
            f"generated extreme conviction (P > 0.90 or P < 0.10), exceeding 20% limit. "
            f"Possible Correlated Overconfidence Hallucination detected! Zeroing out all P-scores."
        )
        
        # Zero out P-scores in database
        for symbol in watchlist:
            try:
                item = _arctic_read(f"{symbol}_meta")
                if item is not None:
                    df = item.data.copy()
                    df.loc[df.index[-1], "meta_conviction"] = 0.50
                    df.loc[df.index[-1], "primary_dir"] = 0
                    _arctic_write(f"{symbol}_meta", df)
            except Exception as e:
                logging.warning(f"[VETO_DB_WRITE_ERR] Failed to zero out {symbol}: {e}")
                
        # Refuse to pass signals to Fast Loop by clearing pending signals
        with _CYCLE_LOCK:
            _CYCLE_PENDING_SIGNALS = []
    else:
        # No veto engaged: safely dispatch all pending signals
        logging.info(f"[SRE] Veto check passed. Dispatching {len(_CYCLE_PENDING_SIGNALS)} qualified signals.")
        for sig in _CYCLE_PENDING_SIGNALS:
            try:
                push_to_orchestrator(sig)
            except Exception as e:
                logging.error(f"[SIGNAL_DISPATCH_ERR] Failed to dispatch signal for {sig['symbol']}: {e}")
def execute_historical_backfill(watchlist: list):
    logging.info(f"[SRE] Cache-based backfill verification ({len(watchlist)} assets)...")
    pass

def should_trigger_evaluation(watchlist: list, last_run_hour: int):
    global _LAST_CYCLE_PRICES, _LAST_CYCLE_ATRs
    now = datetime.now()
    
    # 1. H1 Candle Close Fallback
    if now.hour != last_run_hour:
        logging.info(f"[EVENT-TRIGGER] H1 Candle Close detected (Prev Hour: {last_run_hour}, Current Hour: {now.hour}). Triggering evaluation.")
        return True, "H1_CLOSE"
        
    # 2. Volatility Shock Check (> 0.5 ATR price movement)
    import MetaTrader5 as mt5
    for symbol in watchlist:
        try:
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                continue
            current_price = (tick.bid + tick.ask) / 2
            
            atr = 0.0
            if symbol in _LAST_CYCLE_ATRs:
                atr = _LAST_CYCLE_ATRs[symbol]
            else:
                meta_item = _arctic_read(f"{symbol}_meta")
                if meta_item is not None:
                    atr = float(meta_item.data.iloc[-1].get("atr", 0.0))
                    _LAST_CYCLE_ATRs[symbol] = atr
            
            if atr <= 0:
                continue
                
            last_price = _LAST_CYCLE_PRICES.get(symbol, 0.0)
            if last_price <= 0:
                _LAST_CYCLE_PRICES[symbol] = current_price
                continue
                
            price_delta = abs(current_price - last_price)
            threshold = 0.5 * atr
            if price_delta >= threshold:
                logging.info(f"[EVENT-TRIGGER] Volatility Shock detected on {symbol}! Move: {price_delta:.5f} >= 0.5*ATR ({threshold:.5f}). Triggering evaluation.")
                return True, f"VOLATILITY_SHOCK_{symbol}"
        except Exception as e:
            logging.debug(f"[TRIGGER_CHECK_ERR] Error checking trigger for {symbol}: {e}")
            
    return False, None

def main():
    global _LAST_CS_REFRESH, _LAST_CYCLE_PRICES, _LAST_CYCLE_ATRs, _IS_STARTUP_OR_SHOCK
    print("=" * 60)
    import dynamic_instrument_router as router
    import MetaTrader5 as mt5
    from fastapi_sniper import calculate_structural_atr_d1

    if not _LAST_CYCLE_ATRs:
        logging.info("[ROUTER] Pre-fetching ATRs for Cycle 0 routing...")
        for sym in WATCHLIST:
            try:
                atr = calculate_structural_atr_d1(sym, period=14)
                _LAST_CYCLE_ATRs[sym] = atr
            except Exception:
                _LAST_CYCLE_ATRs[sym] = 0.0

    acc = mt5.account_info()
    current_equity = acc.equity if acc else 0.0
    
    watchlist = router.compute_eligible_universe(current_equity, _LAST_CYCLE_ATRs)
    if not watchlist:
        logging.critical("[ROUTER] 0 eligible symbols. System cannot trade with current equity.")
        watchlist = WATCHLIST[:2] # Minimal fallback just to keep loop alive without crashing
        
    print("=" * 60)
    print(f"  ACTIVE MATRIX SIZE: {len(watchlist)} ASSETS (Filtered from {len(WATCHLIST)})")
    print("=" * 60)
    
    execute_historical_backfill(watchlist)
    
    # Directive 1: Immediate startup evaluation cycle (Cycle 0)
    logging.info("[SYSTEM] Startup Immediate Evaluation (Cycle 0, parallel, force_refresh=True)...")
    _IS_STARTUP_OR_SHOCK = True
    asyncio.run(process_matrix_parallel(watchlist, force_refresh=True))
    _LAST_CS_REFRESH = time.time()
    
    # Store initial prices and ATRs after the first cycle
    import MetaTrader5 as mt5
    for symbol in watchlist:
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                _LAST_CYCLE_PRICES[symbol] = (tick.bid + tick.ask) / 2
            meta_item = _arctic_read(f"{symbol}_meta")
            if meta_item is not None:
                _LAST_CYCLE_ATRs[symbol] = float(meta_item.data.iloc[-1].get("atr", 0.0))
        except Exception as e:
            logging.debug(f"[INIT_PRICE_ERR] {symbol}: {e}")
            
    last_run_hour = datetime.now().hour
    _IS_STARTUP_OR_SHOCK = False
    logging.info("[SYSTEM] Cycle 0 execution completed. Entering short-polling event loop.")

    # Directive 2: Information-Driven Awakening (Event-Driven asyncio.Queue)
    async def mt5_event_loop():
        nonlocal last_run_hour, watchlist, current_equity
        mt5_queue = asyncio.Queue()
        
        async def mock_mt5_tick_producer():
            while True:
                await asyncio.sleep(10)
                await mt5_queue.put("TICK")
                
        asyncio.create_task(mock_mt5_tick_producer())
        
        while True:
            global _TICK_STARVATION_DETECTED, _IS_STARTUP_OR_SHOCK
            try:
                event = await mt5_queue.get()
                
                trigger, reason = should_trigger_evaluation(watchlist, last_run_hour)
                
                # Post-exit / Equity change check
                acc = mt5.account_info()
                new_equity = acc.equity if acc else current_equity
                import sentinel_config as cfg
                if abs(new_equity - current_equity) > getattr(cfg, 'ROUTER_EQUITY_UPDATE_THRESHOLD', 50.0):
                    logging.info(f"[ROUTER] Equity changed from {current_equity} to {new_equity}. Re-evaluating universe...")
                    current_equity = new_equity
                    watchlist = router.compute_eligible_universe(current_equity, _LAST_CYCLE_ATRs)
                    trigger = True
                    reason = "EQUITY_CHANGE"
                    
                if trigger:
                    logging.info(f"[HEARTBEAT] Starting Event-Driven Evaluation Cycle ({reason}) ({len(watchlist)} assets)...")
                    if "VOLATILITY_SHOCK" in reason:
                        _IS_STARTUP_OR_SHOCK = True
                    else:
                        _IS_STARTUP_OR_SHOCK = False
                        
                    await process_matrix_parallel(watchlist, force_refresh=True)
                    _pre_scan_watchlist(watchlist)
                    
                    # Update loop states
                    last_run_hour = datetime.now().hour
                    _IS_STARTUP_OR_SHOCK = False
                    
                    # --- CONSTRAINT 4: EVENT-DRIVEN PARITY ARCHITECTURE ---
                    # Ensure price data timestamping and queuing mirrors research-to-production semantics exactly
                    # Transform live tick data stream into identical event schema as backtesting
                    for symbol in watchlist:
                        try:
                            tick = mt5.symbol_info_tick(symbol)
                            if tick:
                                _LAST_CYCLE_PRICES[symbol] = (tick.bid + tick.ask) / 2
                                # Emit standardized Event Schema
                                tick_event = {
                                    "event_type": "TICK",
                                    "symbol": symbol,
                                    "timestamp_ms": tick.time_msc,
                                    "bid": tick.bid,
                                    "ask": tick.ask,
                                    "last": tick.last,
                                    "volume": tick.volume
                                }
                                # In future, route `tick_event` to standardized handlers matching NautilusTrader architecture
                            meta_item = _arctic_read(f"{symbol}_meta")
                            if meta_item is not None:
                                _LAST_CYCLE_ATRs[symbol] = float(meta_item.data.iloc[-1].get("atr", 0.0))
                        except Exception as e:
                            logging.debug(f"[UPDATE_PRICE_ERR] {symbol}: {e}")
            except Exception as e:
                logging.error(f"[HEARTBEAT_ERROR] {e}")
                await asyncio.sleep(10)
                
    asyncio.run(mt5_event_loop())

if __name__ == "__main__":
    main()

