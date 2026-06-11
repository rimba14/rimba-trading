import os
import sys
import json
import time
import math
import random
import logging
import traceback
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

# Set up logging
logger = logging.getLogger("EdgeDecaySentinel")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

# Ensure directory for state cache exists
os.makedirs("oracle_cache", exist_ok=True)
os.makedirs("pending_diagnostics", exist_ok=True)

# Define file lock helper for concurrent reading/writing
def atomic_write_json(file_path, data):
    temp_path = file_path + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        # Atomic replacement
        os.replace(temp_path, file_path)
    except Exception as e:
        logger.error(f"[LOCK_ERR] Failed to write atomically to {file_path}: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        raise e

def safe_read_json(file_path, retries=5, delay=0.05):
    for i in range(retries):
        try:
            if not os.path.exists(file_path):
                return None
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (PermissionError, json.JSONDecodeError) as e:
            if i == retries - 1:
                logger.warning(f"[LOCK_WARN] Failed to read {file_path} after {retries} retries: {e}")
                raise e
            time.sleep(delay)
    return None

# ==========================================
# 1. BASELINE REGISTRY INTERFACE
# ==========================================
DEFAULT_BASELINES = {
    'v30.98': {
        'max_drawdown': 0.15,
        'max_drawdown_duration': 30, # days
        'daily_return_distribution': [0.005, -0.002, 0.008, 0.001, -0.004, 0.003, -0.001, 0.006, 0.002, -0.003],
        'base_hit_rate': 0.55,
        'base_profit_factor': 1.45,
        'base_expectancy': 0.12, # R-units
        'expected_slippage': 0.0005 # ratio
    }
}

def get_baseline_profile(master_version='v30.98'):
    profile = DEFAULT_BASELINES.get(master_version, DEFAULT_BASELINES['v30.98']).copy()
    try:
        from arcticdb import Arctic
        # Check standard Sentinel cache path or fallback
        store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
        if "telemetry.strategy_decay" in store.list_symbols():
            lib = store["telemetry.strategy_decay"]
            df = lib.read(master_version).data
            if not df.empty:
                row = df.iloc[-1]
                profile = {
                    'max_drawdown': float(row.get('max_drawdown', profile['max_drawdown'])),
                    'max_drawdown_duration': int(row.get('max_drawdown_duration', profile['max_drawdown_duration'])),
                    'daily_return_distribution': list(row.get('daily_return_distribution', profile['daily_return_distribution'])),
                    'base_hit_rate': float(row.get('base_hit_rate', profile['base_hit_rate'])),
                    'base_profit_factor': float(row.get('base_profit_factor', profile['base_profit_factor'])),
                    'base_expectancy': float(row.get('base_expectancy', profile['base_expectancy'])),
                    'expected_slippage': float(row.get('expected_slippage', profile['expected_slippage'])),
                }
    except Exception as e:
        logger.debug(f"[ARCTIC_READ_DEBUG] Could not fetch strategy decay baseline from ArcticDB: {e}. Using local fallback.")
    return profile

def save_baseline_profile(master_version, profile):
    try:
        from arcticdb import Arctic
        store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
        lib = store["telemetry.strategy_decay"]
        df = pd.DataFrame([profile])
        lib.write(master_version, df)
        logger.info(f"[ARCTIC_WRITE] Saved baseline profile for {master_version} to ArcticDB.")
    except Exception as e:
        logger.debug(f"[ARCTIC_WRITE_DEBUG] Could not save baseline profile to ArcticDB: {e}")

# ==========================================
# 2. PERFORMANCE CONE ENGINE (BLOCK BOOTSTRAP)
# ==========================================
def moving_block_bootstrap(returns, block_size, num_paths=1000, path_len=90):
    n = len(returns)
    if n < block_size:
        return np.random.choice(returns, size=(num_paths, path_len), replace=True)
    
    num_blocks_needed = math.ceil(path_len / block_size)
    valid_start_indices = np.arange(0, n - block_size + 1)
    
    bootstrap_paths = []
    for _ in range(num_paths):
        path = []
        for _ in range(num_blocks_needed):
            start_idx = np.random.choice(valid_start_indices)
            block = returns[start_idx : start_idx + block_size]
            path.extend(block)
        bootstrap_paths.append(path[:path_len])
    
    return np.array(bootstrap_paths)

def compute_drawdown_percentiles(bootstrap_paths):
    # Convert returns to equity curves starting at 1.0
    equity_paths = np.cumprod(1.0 + bootstrap_paths, axis=1)
    
    drawdown_paths = []
    for path in equity_paths:
        peaks = np.maximum.accumulate(path)
        # Avoid zero division
        peaks = np.where(peaks <= 0, 1e-9, peaks)
        dd = (peaks - path) / peaks
        drawdown_paths.append(dd)
    
    drawdown_paths = np.array(drawdown_paths)
    
    # Compute 5th, 50th, and 95th percentile curves at each step
    p5 = np.percentile(drawdown_paths, 5, axis=0)
    p50 = np.percentile(drawdown_paths, 50, axis=0)
    p95 = np.percentile(drawdown_paths, 95, axis=0)
    
    return p5, p50, p95

# ==========================================
# 3. ROLLING METRICS TRACKER
# ==========================================
def fetch_rolling_deals(window_days=90):
    # Try to fetch actual closed trade returns from MT5
    if not mt5.initialize():
        mt5.initialize()
    
    end_time = datetime.now()
    start_time = end_time - timedelta(days=window_days)
    
    deals = mt5.history_deals_get(start_time, end_time)
    if not deals:
        return []
    
    # Filter magic number 777 or general trades
    valid_deals = []
    for d in deals:
        if d.magic in [777, 142, 17300] or d.entry == mt5.DEAL_ENTRY_OUT:
            valid_deals.append(d)
    return valid_deals

def calculate_rolling_metrics(deals, baseline_profile, window_days=90):
    if not deals:
        # Fallback baseline returns
        logger.warning("[TRACKER] No recent deals found. Reverting to baseline simulation parameters.")
        mock_returns = baseline_profile['daily_return_distribution']
        rolling_sharpe = 1.5
        max_dd_depth = 0.02
        max_dd_duration = 5
        hit_rate = baseline_profile['base_hit_rate']
        profit_factor = baseline_profile['base_profit_factor']
        expectancy = baseline_profile['base_expectancy']
        avg_slippage = baseline_profile['expected_slippage']
        return {
            'sharpe': rolling_sharpe,
            'max_dd_depth': max_dd_depth,
            'max_dd_duration': max_dd_duration,
            'hit_rate': hit_rate,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
            'avg_slippage': avg_slippage,
            'daily_returns': mock_returns
        }

    # Extract daily marked-to-market or deal returns
    # We compile the daily profit & loss percentages based on account balance
    df = pd.DataFrame([{
        'time': datetime.fromtimestamp(d.time, timezone.utc),
        'profit': d.profit,
        'volume': d.volume,
        'symbol': d.symbol,
    } for d in deals])
    
    # Group by date to get daily profit
    df['date'] = df['time'].dt.date
    daily_pnl = df.groupby('date')['profit'].sum()
    
    # Approximate account balance
    account_info = mt5.account_info()
    balance = account_info.balance if account_info else 10000.0
    if balance <= 0:
        balance = 10000.0
        
    daily_returns = (daily_pnl / balance).tolist()
    
    # Compute rolling metrics
    returns_arr = np.array(daily_returns)
    mean_ret = np.mean(returns_arr) if len(returns_arr) > 0 else 0.0
    std_ret = np.std(returns_arr) if len(returns_arr) > 1 else 1e-9
    if std_ret == 0:
        std_ret = 1e-9
    
    # Annualized Sharpe (assuming 252 trading days)
    rolling_sharpe = float((mean_ret / std_ret) * math.sqrt(252)) if len(returns_arr) > 1 else 1.0
    
    # Calculate Max Drawdown Depth & Duration
    cum_equity = np.cumprod(1.0 + returns_arr)
    peaks = np.maximum.accumulate(cum_equity)
    drawdowns = (peaks - cum_equity) / peaks
    max_dd_depth = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
    
    # Duration underwater (max consecutive days where drawdown > 0)
    underwater = drawdowns > 0
    max_dd_duration = 0
    current_duration = 0
    for val in underwater:
        if val:
            current_duration += 1
            max_dd_duration = max(max_dd_duration, current_duration)
        else:
            current_duration = 0
            
    # Trade-level drift
    wins = df[df['profit'] > 0]
    losses = df[df['profit'] <= 0]
    
    total_trades = len(df)
    hit_rate = float(len(wins) / total_trades) if total_trades > 0 else 0.5
    
    sum_wins = float(wins['profit'].sum())
    sum_losses = float(abs(losses['profit'].sum()))
    profit_factor = float(sum_wins / sum_losses) if sum_losses > 0 else 1.0
    
    avg_win = float(wins['profit'].mean()) if len(wins) > 0 else 0.0
    avg_loss = float(abs(losses['profit'].mean())) if len(losses) > 0 else 1e-9
    expectancy = float((hit_rate * avg_win) - ((1.0 - hit_rate) * avg_loss))
    
    # Slippage calculations (Delta between modeled mid and execution price)
    # Modeled mid price is compared against actual deal price.
    # For simulation, we can query logs or provide a rolling average of slippage
    avg_slippage = baseline_profile['expected_slippage'] # fallback
    
    return {
        'sharpe': rolling_sharpe,
        'max_dd_depth': max_dd_depth,
        'max_dd_duration': max_dd_duration,
        'hit_rate': hit_rate,
        'profit_factor': profit_factor,
        'expectancy': expectancy,
        'avg_slippage': avg_slippage,
        'daily_returns': daily_returns
    }

# ==========================================
# 4. CONSTITUTIONAL BREACH CLASSIFIER
# ==========================================
def classify_breach_status(metrics, baseline_profile, p5_dd, p95_dd):
    # Threshold constraints:
    # SOFT_BREACH: Rolling 90-day Sharpe falls below 5th backtest percentile (approx Sharpe < 0.8),
    # OR current drawdown exceeds 1.0x historical max drawdown.
    # HARD_BREACH: Current drawdown exceeds 1.5x backtest maximum drawdown,
    # OR duration underwater exceeds 1.5x longest historical stagnations (e.g. 1.5 * baseline max stagnation).
    
    max_dd_baseline = baseline_profile['max_drawdown']
    max_stagnation_baseline = baseline_profile['max_drawdown_duration']
    
    is_hard = False
    is_soft = False
    
    if metrics['max_dd_depth'] >= 1.5 * max_dd_baseline:
        is_hard = True
    elif metrics['max_dd_duration'] >= 1.5 * max_stagnation_baseline:
        is_hard = True
        
    if not is_hard:
        if metrics['sharpe'] < 0.8: # approximate 5th percentile Sharpe fallback
            is_soft = True
        elif metrics['max_dd_depth'] >= 1.0 * max_dd_baseline:
            is_soft = True
            
    if is_hard:
        return "HARD_BREACH"
    elif is_soft:
        return "SOFT_BREACH"
    return "NORMAL_VARIANCE"

# ==========================================
# 5. REGIME-CONGRUENT DIAGNOSIS ENGINE
# ==========================================
def run_regime_diagnosis(symbol="Directive_Meridian", start_time_epoch=None):
    # Default parameters
    hmm_state_transition = False
    new_deployment = False
    cluster_correlation = False
    
    # 1. HMM Check
    try:
        from gitagent_hmm import get_current_hmm_state
        state = get_current_hmm_state()
        # Mock checks or check HMM transition cache
        if state in ["TURBULENT", "MEAN_REVERTING"]:
            hmm_state_transition = True
    except:
        hmm_state_transition = True # Default fallback for diagnosis safety
        
    # 2. Time-Since-Deployment Check
    if start_time_epoch:
        age_days = (time.time() - start_time_epoch) / 86400
        if age_days < 21: # Deployed within 3 weeks
            new_deployment = True
            
    # 3. Cluster correlation checks
    # Check if multiple currency or index assets are showing simultaneous drawdown
    try:
        positions = mt5.positions_get()
        if positions and len(positions) >= 3:
            cluster_correlation = True
    except:
        pass
        
    # Classify diagnosis type
    if hmm_state_transition:
        return "REGIME_SHIFT"
    elif new_deployment:
        return "OVERFITTING"
    return "MARKET_MICROSTRUCTURE_DECAY"

# ==========================================
# 6. INTEGRATION CACHE HOOKS & STATE EMITTER
# ==========================================
def run_edge_decay_sentinel(master_version='v30.98', deployment_time=None):
    logger.info(f"[SENTINEL] Starting Edge Decay Sentinel Sweep for {master_version}...")
    
    # Load baselines
    baseline = get_baseline_profile(master_version)
    
    # Run performance cone simulation (Moving Block Bootstrap)
    daily_baseline_returns = baseline['daily_return_distribution']
    bootstrap_paths = moving_block_bootstrap(daily_baseline_returns, block_size=5, num_paths=1000, path_len=90)
    p5_dd, p50_dd, p95_dd = compute_drawdown_percentiles(bootstrap_paths)
    
    # Fetch actual closed trades & calculate rolling metrics
    deals = fetch_rolling_deals(window_days=90)
    metrics = calculate_rolling_metrics(deals, baseline)
    
    # Classify status
    status = classify_breach_status(metrics, baseline, p5_dd, p95_dd)
    
    # Run Diagnosis if breach detected
    diagnosis = "NORMAL"
    if status == "HARD_BREACH":
        diagnosis = run_regime_diagnosis("Directive_Meridian", deployment_time)
        logger.critical(f"[SENTINEL] HARD BREACH CLASSIFIED. DIAGNOSIS: {diagnosis}")
    elif status == "SOFT_BREACH":
        logger.warning("[SENTINEL] SOFT BREACH CLASSIFIED. Applying safety buffers.")
        
    # Construct output payload
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "master_version": master_version,
        "global_status": "NORMAL" if status == "NORMAL_VARIANCE" else status,
        "module_tier": {
            "Directive_Meridian": status
        },
        "agent_tier": {
            "MixTS_v1": "QUARANTINED" if status == "HARD_BREACH" else "ACTIVE",
            "TimesNet_Oracle": "ACTIVE"
        },
        "diagnosis": diagnosis
    }
    
    # Emit state atomically
    cache_path = os.path.join("oracle_cache", "edge_decay_state.json")
    atomic_write_json(cache_path, payload)
    logger.info(f"[SENTINEL] Edge Decay state emitted successfully to {cache_path}")
    
    # Return metrics for validation/unit tests
    return metrics, payload

if __name__ == '__main__':
    # For standalone execution/testing
    metrics, payload = run_edge_decay_sentinel()
    print(json.dumps(payload, indent=4))
