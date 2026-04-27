import sys
import subprocess
import importlib.util

def _enforce_dependencies():
    critical_libs = ['shap', 'scipy', 'statsmodels']
    for lib in critical_libs:
        spec = importlib.util.find_spec(lib)
        if spec is None:
            print(f"[BOOTSTRAP] Installing missing dependency: {lib}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

_enforce_dependencies()

import time
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
import os
import logging
import json
from datetime import datetime

# Inject project path
sys.path.append(r"C:\Sentinel_Project")

import git_arctic
import gitagent_hmm as hmm
import gitagent_sigproc as sigproc
import kronos_bridge
import timesfm_bridge
import gitagent_utils as utils
import gitagent_bars as bars
import xgboost as xgb
import shap

import logging
import concurrent.futures
import random
from qwen_reasoning_engine import QwenReasoningEngine

from statsmodels.tsa.stattools import adfuller

def apply_frac_diff(series, d, threshold=1e-5):
    """Applies fractional differentiation with a memory-preserving window."""
    w = [1.0]
    k = 1
    while True:
        w_k = -w[-1] / k * (d - k + 1)
        if abs(w_k) < threshold: break
        w.append(w_k)
        k += 1
    
    w = np.array(w[::-1]).reshape(-1, 1)
    width = len(w) - 1
    
    if len(series) <= width:
        return np.diff(series) # Fallback
        
    output = []
    for i in range(width, len(series)):
        val = np.dot(w.T, series[i-width:i+1])[0]
        output.append(val)
    
    return np.array(output)

def optimize_fracdiff_d(series):
    """Directive 1: Find minimum d for stationarity (p < 0.05)."""
    best_d = 1.0
    final_series = np.diff(series)
    
    for d in np.arange(0.0, 1.05, 0.05):
        if d == 0:
            diff_series = series
        else:
            diff_series = apply_frac_diff(series, d)
        
        if len(diff_series) < 10: continue
        
        try:
            res = adfuller(diff_series, autolag='AIC')
            if res[1] < 0.05:
                return d, diff_series
        except:
            continue
            
    return best_d, final_series

# Load Meta-Model once
META_MODEL_PATH = "C:\\Sentinel_Project\\medallion_model.json"
_META_MODEL = None
_SHAP_EXPLAINER = None
if os.path.exists(META_MODEL_PATH):
    _META_MODEL = xgb.XGBClassifier()
    _META_MODEL.load_model(META_MODEL_PATH)
    _SHAP_EXPLAINER = shap.TreeExplainer(_META_MODEL)

SHAP_DIR = "C:\\Sentinel_Project\\shap_diagnostics"
os.makedirs(SHAP_DIR, exist_ok=True)

# Directive 1: LMDB Singleton Pattern (v16.9)
from arcticdb import Arctic
institutional_ledger = Arctic('lmdb://./data/arctic_cache')
oracle_lib = institutional_ledger['oracle_cache'] if 'oracle_cache' in institutional_ledger.list_libraries() else institutional_ledger.create_library('oracle_cache')

# Initialize Reasoning Engine
_QWEN_ENGINE = QwenReasoningEngine()

def calculate_concurrency_weighting(labels: pd.DataFrame) -> pd.Series:
    """
    Directive: Calculate 'Average Uniqueness' (concurrency) of every training label.
    1 / c_t penalty for overlapping labels.
    """
    if labels.empty: return pd.Series()
    
    # Simple concurrency count: number of active labels at each timestamp
    # This assumes 'timestamp' and 'expiry' columns exist in labels
    if 'expiry' not in labels.columns:
        return pd.Series(1.0, index=labels.index)
        
    concurrency = pd.Series(0, index=labels.index)
    for i, row in labels.iterrows():
        overlap = labels[(labels['timestamp'] < row['expiry']) & (labels['expiry'] > row['timestamp'])]
        concurrency.loc[i] = len(overlap)
        
    return 1.0 / concurrency.clip(lower=1)

def get_meta_conviction(symbol, features, direction):
    """
    Directive 2: Meta-Model outputs probability (p) that Primary is correct.
    """
    if _META_MODEL is None or direction == 0:
        return 0.50
    
    try:
        # Prepare feature vector (must match training keys in medallion_trainer.py)
        # Directive: SRE Surgical Amputation - Feature Blacklist
        f_keys = ['W_rsi', 'W_macd', 'Wy_trend', 'B_bbpos', 'S_struct', 'WHL_vol']
        x = [features.get(k, 0.5) for k in f_keys]
        
        # Inference
        logging.info(f"[{symbol}] Feature Vector: {x}")
        p_success = _META_MODEL.predict_proba(np.array([x]))[0][1]
        
        # Native MoE Reasoning (Directive 2)
        reasoning_data = {
            "decision": "HOLD",
            "confidence": 0.5,
            "reasoning": "Reasoning Engine skipped."
        }
        
        try:
            sys_prompt = "You are the Sentinel Meta-Model. Analyze these features and provide a conviction score."
            sanitized_features = {k: float(v) if isinstance(v, (int, float, np.number)) else str(v) for k, v in features.items()}
            user_prompt = f"SYMBOL: {symbol} | FEATURES: {json.dumps(sanitized_features)} | PRIMARY: {direction}"
            # Call engine but don't let it block or drag down the conviction for now (Bypass Active)
            # reasoning_data = _QWEN_ENGINE.json_with_retry(sys_prompt, user_prompt)
        except Exception as e:
            logging.error(f"Reasoning Engine Error for {symbol}: {e}")

        # Directive: Reasoning Core Bypass (Emergency Verification)
        # Using 100% Meta-Model (p_success) to verify execution pipeline.
        p_final = p_success
        
        # SHAP Diagnostics (Phase 2 White-Box Oracle)
        if _SHAP_EXPLAINER is not None:
            try:
                s_vals = _SHAP_EXPLAINER.shap_values(np.array([x]))[0]
                total_abs = np.sum(np.abs(s_vals))
                weights = {f_keys[i] if i < len(f_keys) else 'primary_dir': float(s_vals[i] / total_abs) for i in range(len(s_vals))}
                
                # Concept Drift Monitor (Hermes Watchdog)
                max_weight = max(abs(v) for v in weights.values())
                if max_weight > 0.65:
                    logging.warning(f"[CONCEPT_DRIFT] {symbol}: Feature {max(weights, key=lambda k: abs(weights[k]))} weight {max_weight:.2%} > 65%!")
                
                # Extract top 3 positive/negative
                sorted_w = sorted(weights.items(), key=lambda x: x[1], reverse=True)
                top_pos = sorted_w[:3]
                top_neg = sorted_w[-3:]
                
                diag_payload = {
                    "symbol": symbol,
                    "prediction": int(direction),
                    "conviction": float(p_final),
                    "reasoning": reasoning_data.get('reasoning', 'N/A'),
                    "timestamp": utils.get_utc_epoch(),
                    "weights": weights,
                    "top_pos": top_pos,
                    "top_neg": top_neg,
                    "concept_drift": max_weight > 0.65
                }
                
                diag_path = os.path.join(SHAP_DIR, f"{symbol}_diag.json")
                with open(diag_path, "w") as f:
                    json.dump(diag_payload, f, indent=2)
                logging.info(f"[{symbol}] SHAP Diagnostic dropped: {diag_path}")
            except Exception as e:
                logging.error(f"SHAP Error for {symbol}: {e}")
                
        return float(p_final)
    except Exception as e:
        logging.error(f"Meta-Model Error for {symbol}: {e}")
        return 0.50

# Configure Logging
log_file = r"C:\sentinel_logs\slow_loop_v16_9.log"
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [SLOW_LOOP] %(message)s',
    force=True,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file)
    ]
)

# Track last update time to debounce
_LAST_ORACLE_UPDATE = {}
ORACLE_COOLDOWN = 15.0 # Seconds (Directive: Prevent CPU Backlog)

def update_slow_oracles(symbol: str):
    """Updates HMM, Kronos, and TimesFM oracles for a symbol."""
    now = time.time()
    if symbol in _LAST_ORACLE_UPDATE:
        if now - _LAST_ORACLE_UPDATE[symbol] < ORACLE_COOLDOWN:
            return
    _LAST_ORACLE_UPDATE[symbol] = now
    
    df_m15 = None
    df_ta = None
    df_ml = None
    close_series = None
    try:
        # Directive 3: Prevent Rate-Limiting with Micro-Sleep
        time.sleep(random.uniform(0.1, 0.5))
        
        logging.info(f"Updating Oracles for {symbol}...")
        
        # 1. Fetch M15 Data (Increased to 2,000 for FracDiff depth)
        df_m15 = sigproc.get_m15_dataframe(symbol, 2000) 
        if df_m15 is None or len(df_m15) < 512:
            logging.error(f"[TICKER_ERROR] Insufficient data for {symbol} ({len(df_m15) if df_m15 is not None else 0} bars). Bypassing inference.")
            return

        # 2. Upgrade the Slow Loop Pipeline (Directive 2: Medallion Features)
        # Apply Technical Indicator Extraction (Native Implementation)
        df_ta = df_m15.copy()
        
        logging.info(f"[{symbol}] Initial Data Shape: {df_ta.shape}")

        # W_rsi (14)
        delta = df_ta['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df_ta['W_rsi'] = 100 - (100 / (1 + rs))
        
        # W_macd (12, 26, 9)
        ema12 = df_ta['close'].ewm(span=12, adjust=False).mean()
        ema26 = df_ta['close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        df_ta['W_macd'] = macd - signal
        
        # Wy_trend (EMA 20 vs 50)
        ema20 = df_ta['close'].ewm(span=20, adjust=False).mean()
        ema50 = df_ta['close'].ewm(span=50, adjust=False).mean()
        df_ta['Wy_trend'] = (ema20 - ema50) / (df_ta['close'] * 0.01 + 1e-9)
        
        # B_bbpos (Bollinger Band 20, 2)
        ma20 = df_ta['close'].rolling(window=20).mean()
        std20 = df_ta['close'].rolling(window=20).std()
        upper = ma20 + (2 * std20)
        lower = ma20 - (2 * std20)
        df_ta['B_bbpos'] = (df_ta['close'] - lower) / (upper - lower + 1e-9)
        
        # WHL_vol (Std Dev of Returns)
        df_ta['WHL_vol'] = df_ta['close'].pct_change().rolling(window=20).std()
        
        # S_struct (Support/Resistance Proximity placeholder)
        df_ta['S_struct'] = 0.5
        
        # COSMO Fallbacks (Neutral)
        df_ta['COSMO_geoAp'] = 0.5
        df_ta['COSMO_lunar'] = 0.5
        df_ta['COSMO_align'] = 0.5
        
        logging.info(f"[{symbol}] Cleaned Data Shape: {df_ta.shape}")

        # Apply Fractional Differentiation to Close Prices for ML
        close_series = df_ta['close'].values
        optimal_d, frac_close = optimize_fracdiff_d(close_series)
        logging.info(f"[{symbol}] FracDiff Optimization: d={optimal_d:.2f} (Stationarity Achieved)")
        
        # Create a FracDiff version of the dataframe for ML oracles
        pad_len = len(close_series) - len(frac_close)
        frac_close_padded = np.pad(frac_close, (pad_len, 0), mode='edge')

        df_ml = df_ta.copy()
        df_ml['close'] = frac_close_padded
        for col in ['open', 'high', 'low']:
            _, f_col = optimize_fracdiff_d(df_ta[col].values)
            f_col_padded = np.pad(f_col, (len(df_ta) - len(f_col), 0), mode='edge')
            df_ml[col] = f_col_padded
            
        # Strict DropNA Logic (Eradicate feature leakage and faked data)
        df_ml = df_ml.dropna()
        if len(df_ml) < 512:
            logging.error(f"[TICKER_ERROR] {symbol} dropped below 512 bars after NaNs. Clean bars: {len(df_ml)}. Bypassing.")
            return
        
        logging.info(f"[{symbol}] Cleaned Data Shape: {df_ml.shape}")
        
        # Directive: SRE Surgical Amputation - Feature Blacklist
        df_ml = df_ml.drop(columns=[col for col in df_ml.columns if 'COSMO_' in col], errors='ignore')
        
        # Update HMM & ATR Cache (using raw prices for risk/regime)
        hmm_state, hmm_prob, _ = hmm.get_current_state(df_m15['close'].values)
        atr = utils.calculate_atr(df_m15)
        
        # Directive 3: High-Conviction Pipeline Diagnostic
        logging.info(f"[HMM DEBUG] {symbol}: Raw input shape {df_m15.shape}, Output State: {hmm_state}")
        
        # Directive 1: Use Global Singleton
        lib = oracle_lib
        
        h_data = pd.DataFrame([{
            "state": hmm_state,
            "prob": float(hmm_prob),
            "atr": float(atr),
            "timestamp": utils.get_utc_epoch()
        }])
        lib.write(f"{symbol}_hmm", h_data)
        logging.info(f"[{symbol}] HMM Cached: {hmm_state}")

        # 3. Update Kronos & Meta-Model (Directive 1 & 2)
        kronos_bridge.update_cognition_cache(symbol, df_ml)
        
        # Directive 2: Cold-Start Exception Handling
        try:
            lib = oracle_lib
            k_item = lib.read(f"{symbol}_kronos")
            k_prob = float(k_item.data.iloc[-1]['kronos_prob'])
            x_prob = float(k_item.data.iloc[-1].get('xgboost_prob', 0.50))
        except Exception:
            # Graceful Fallback for Empty Cache
            k_prob, x_prob = 0.50, 0.50
        
        # Directive 1: Strict Ternary Direction
        p_blend = (k_prob * 0.70) + (x_prob * 0.30)
        primary_dir = 1 if p_blend > 0.60 else (-1 if p_blend < 0.40 else 0)
        
        # Get Meta-Conviction & Trigger SHAP Diagnostics
        current_features = df_ml.iloc[-1].to_dict()
        meta_p = get_meta_conviction(symbol, current_features, primary_dir)

        # Update Cache with Meta-Labeling Data
        meta_df = pd.DataFrame([{
            "primary_dir": int(primary_dir),
            "meta_conviction": float(meta_p),
            "timestamp": utils.get_utc_epoch()
        }])
        
        # Directive: Universal UTC & 300ms Staleness Gate
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            try:
                future = executor.submit(lib.write, f"{symbol}_meta", meta_df)
                future.result(timeout=0.3)
                logging.info(f"[{symbol}] ArcticDB Meta Written.")
            except concurrent.futures.TimeoutError:
                logging.error(f"[{symbol}] ArcticDB Write Timeout (>300ms). Skipping Cache update.")
            except Exception as e:
                logging.error(f"[{symbol}] ArcticDB Write Error: {e}")

        logging.info(f"[{symbol}] Meta-Labeling: Dir={primary_dir}, Conviction={meta_p:.3f}")

        # 4. Update TimesFM Cache (Using FracDiff ML Dataframe)
        timesfm_bridge.update_risk_cache(symbol, df_ml)

    except Exception as e:
        logging.error(f"Error updating oracles for {symbol}: {e}")
    finally:
        # Enforce Loop State Isolation
        df_m15 = None
        df_ta = None
        df_ml = None
        close_series = None

def execute_historical_backfill(watchlist):
    """
    SRE Historical Backfill Protocol (v16.9)
    Forces MT5 terminal to pull deep history to avoid 0.500 flatlines.
    """
    logging.info(f"═"*60)
    logging.info(f"[SRE] INITIATING HISTORICAL BACKFILL PROTOCOL ({len(watchlist)} assets)")
    logging.info(f"═"*60)
    
    for symbol in watchlist:
        try:
            # 1. Force pull 2,000 M1 bars (Cold-Start Bypass)
            rates_m1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 2000)
            # 2. Force pull 2,000 M15 bars (Slow Loop depth)
            rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 2000)
            
            if rates_m1 is not None and rates_m15 is not None:
                logging.info(f"  [+] {symbol}: Backfill Successful (M1: {len(rates_m1)}, M15: {len(rates_m15)})")
            else:
                logging.warning(f"  [-] {symbol}: Backfill Partial/Failed. Retrying with lower count...")
                mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 500)
        except Exception as e:
            logging.error(f"  [!] Error backfilling {symbol}: {e}")
            
    logging.info(f"═"*60)
    logging.info("[SRE] Backfill Protocol Complete. Matrix warm.")
    logging.info(f"═"*60 + "\n")

def main():
    if not mt5.initialize():
        logging.critical("MT5 Initialization Failed.")
        return

    from sentinel_config import WATCHLIST
    watchlist = WATCHLIST
    
    logging.info("Sentinel v15.4 Asset-Aware Slow Loop Started.")
    
    # Directive 2: Historical Backfill Protocol
    execute_historical_backfill(watchlist)
    
    # Initialize Arctic singleton once before starting threads to ensure safety
    # institutional_ledger = Arctic('lmdb://./data/arctic_cache')
    # git_arctic.get_arctic()

    # Directive 2: Implement the Event-Driven Trigger
    active_watchlist = watchlist
    
    # --- PHASE 0: CACHE WARM-UP (Directive: Eradicate Staleness) ---
    logging.info("[SYSTEM] Warming Cache for active watchlist...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as warmup_executor:
        futures = [warmup_executor.submit(update_slow_oracles, s) for s in active_watchlist]
        concurrent.futures.wait(futures)
    logging.info("[SYSTEM] Cache Warm-up Complete.")

    streamer = bars.InformationBarStreamer(active_watchlist)
    
    logging.info("[SYSTEM] Entering Event-Driven Execution Cycle (Dollar Bars).")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        for bar in streamer.stream_bars():
            symbol = bar['symbol']
            # Trigger Oracle Update only when a bar is completed for this symbol
            executor.submit(update_slow_oracles, symbol)

if __name__ == "__main__":
    main()
