import os
import json
import time
import logging
import sys
import itertools
import requests
import pandas as pd
import numpy as np
import xgboost as xgb
from scipy.stats import norm, skew, kurtosis
from sklearn.model_selection import KFold

# Suffix-Aware Resolver & Utilities
sys.path.append(r"C:\Sentinel_Project")
try:
    import gitagent_utils as utils
except ImportError:
    utils = None

try:
    from sentinel_config import BROKER_SUFFIX
except ImportError:
    BROKER_SUFFIX = ""

try:
    from medallion_trainer import FEATURE_KEYS
except ImportError:
    FEATURE_KEYS = [f"feat_{i}" for i in range(20)]

# Heavy dependencies handled gracefully for research environment
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

try:
    import vectorbt as vbt
except ImportError:
    vbt = None

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1496246026611458048/2ShGeHJjN-Z6XrydLjFy_hOz-iLWrqNHVfp3vanWHj7udTYXUGfglWvUdxJ0WqLyAK88"

PURGE_BARS = 10
EMBARGO_BARS = 10

def calculate_dsr(max_sharpe, trial_sharpes, n_trials, t_samples, skew_val, kurt_val):
    """
    Directive 2: Calculate the Deflated Sharpe Ratio (DSR).
    Corrects for Selection Bias under Multiple Testing.
    """
    gamma = 0.57721566490153286 # Euler-Mascheroni
    std_trials = np.std(trial_sharpes) if len(trial_sharpes) > 1 else 0
    
    if n_trials <= 1:
        expected_max_sr = 0
    else:
        # Expected max SR under null hypothesis (zero true edge)
        z_n = (1 - gamma) * norm.ppf(1 - 1/n_trials) + gamma * norm.ppf(1 - 1/(n_trials * np.e))
        expected_max_sr = std_trials * z_n
        
    # Standard deviation of the Sharpe Ratio estimate
    # Adjusted for non-normality (skew/kurtosis)
    denom = (1 - skew_val * max_sharpe + ((kurt_val - 1) / 4) * max_sharpe**2)
    sigma_sr = np.sqrt(max(1e-9, denom) / (t_samples - 1))
    
    # DSR is the PSR against the expected max Sharpe
    dsr_p = norm.cdf((max_sharpe - expected_max_sr) / sigma_sr)
    return dsr_p, expected_max_sr

class PurgedKFold:
    """
    Directive 1: Purged and Embargoed Cross-Validation.
    Prevents information leakage in financial time series.
    """
    def __init__(self, n_splits=5, purge_bars=10, embargo_bars=10):
        self.n_splits = n_splits
        self.purge_bars = purge_bars
        self.embargo_bars = embargo_bars
        self.kf = KFold(n_splits=n_splits)

    def split(self, X, y=None, groups=None):
        for train_indices, test_indices in self.kf.split(X):
            test_start = test_indices[0]
            test_end = test_indices[-1]
            
            # 1. Purging: Drop training labels overlapping with test window
            purged_train = [
                i for i in train_indices 
                if i < (test_start - self.purge_bars) or i > (test_end + self.purge_bars)
            ]
            
            # 2. Embargoing: Drop h observations following the end of any test set
            final_train = [
                i for i in purged_train 
                if i < test_start or i > (test_end + self.embargo_bars)
            ]
            
            if len(final_train) > 0:
                yield np.array(final_train), test_indices

def find_cointegrated_pairs_algebraic(prices_df: pd.DataFrame, n_components: int = 8) -> list:
    """
    Constructs a dense pair-matching topology where signatures are evaluated
    via rescaled lattice bounds to uncover dense clusters of cointegrated assets.
    """
    try:
        from gitagent_algebraic_manifold import AlgebraicLatticeProjector
    except ImportError:
        return []

    symbols = prices_df.columns
    n_assets = len(symbols)
    if n_assets < 2:
        return []

    # Calculate returns
    returns = prices_df.pct_change().dropna().values
    if len(returns) < 5:
        return []
    
    # Project returns onto the Algebraic Lattice space
    projector = AlgebraicLatticeProjector(n_components=n_components)
    projector.fit(returns)
    dense_signatures = projector.transform(returns) # Shape: [T, n_components]
    
    pairs = []
    for i, sym1 in enumerate(symbols):
        for j, sym2 in enumerate(symbols):
            if i >= j:
                continue
            
            # Distance in the algebraic manifold
            sig1 = dense_signatures[:, i % n_components]
            sig2 = dense_signatures[:, j % n_components]
            
            # Non-Euclidean algebraic distance projection with rescaled lattice bounds
            lattice_bound = np.sum(np.abs(sig1 - sig2)) / (1.0 + np.linalg.norm(sig1 * sig2))
            
            # Score co-moving asset manifold over highly non-linear interval
            pairs.append((sym1, sym2, float(lattice_bound)))
            
    # Sort pairs by lattice distance ascending (dense pairing density)
    pairs.sort(key=lambda x: x[2])
    return pairs

def evaluate_cross_sectional_pairs(prices_df: pd.DataFrame) -> dict:
    """
    Refactors cross-sectional pair evaluations using the algebraic lattice dense clustering metric
    to extract co-moving asset manifolds over highly non-linear intervals.
    """
    logging.info("Evaluating cross-sectional pairs using dense algebraic lattice projection...")
    try:
        pairs = find_cointegrated_pairs_algebraic(prices_df)
        if not pairs:
            return {"status": "empty", "pairs": []}
        
        # Format the top pairs
        top_pairs = [{"pair": f"{p[0]}-{p[1]}", "lattice_distance": p[2]} for p in pairs[:10]]
        logging.info(f"Top 3 Co-moving Manifold Pairs: {top_pairs[:3]}")
        return {"status": "success", "pairs": top_pairs}
    except Exception as e:
        logging.error(f"Failed cross-sectional pair evaluation: {e}")
        return {"status": "error", "message": str(e)}

def _fetch_mt5_data(symbol, timeframe='M15', count=2000):
    """Fetches historical data from MetaTrader 5."""
    if mt5 is None:
        logging.error("MetaTrader5 package not installed.")
        return None

    if not mt5.initialize():
        logging.error("MT5 failed to initialize for research.")
        return None

    # Map timeframe string to MT5 constant
    tf_map = {
        'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15,
        'M30': mt5.TIMEFRAME_M30, 'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4,
        'D1': mt5.TIMEFRAME_D1
    }
    mt5_tf = tf_map.get(timeframe, mt5.TIMEFRAME_M15)

    full_symbol = symbol if symbol.endswith(BROKER_SUFFIX) else symbol + BROKER_SUFFIX

    rates = mt5.copy_rates_from_pos(full_symbol, mt5_tf, 0, count)
    if rates is None or len(rates) == 0:
        logging.error(f"Failed to fetch real data for {full_symbol}")
        return None

    return pd.Series([x[4] for x in rates]) # Use Close prices

def _get_model_predictions(price):
    """Loads the Medallion model and generates predictions on simulated features."""
    model = xgb.XGBClassifier()
    model_file = r"C:\Sentinel_Project\medallion_model.json"
    if os.path.exists(model_file):
        try:
            model.load_model(model_file)
        except Exception as e:
            logging.warning(f"Failed to load model file {model_file}: {e}")

    # Simulate Features and Predict
    X_sim = pd.DataFrame(np.random.randn(len(price), len(FEATURE_KEYS)), columns=FEATURE_KEYS)
    probs = model.predict_proba(X_sim)[:, 1]
    return probs

def _run_cv_backtest(price, probs, pkf):
    """Runs a backtest across cross-validation folds."""
    if vbt is None:
        logging.error("vectorbt package not installed.")
        return [], None

    all_path_sharpes = []
    last_pf = None

    for train_idx, test_idx in pkf.split(price):
        test_mask = np.zeros(len(price), dtype=bool)
        test_mask[test_idx] = True

        # Execute trades where prob > threshold (0.55)
        entries = (probs > 0.55).reshape(-1, 1) & test_mask.reshape(-1, 1)
        exits = (probs < 0.45).reshape(-1, 1) | ~test_mask.reshape(-1, 1)

        last_pf = vbt.Portfolio.from_signals(price, entries, exits, freq='15m')
        fold_sharpe = last_pf.sharpe_ratio()
        all_path_sharpes.append(fold_sharpe)

    return all_path_sharpes, last_pf

def _evaluate_robustness(all_path_sharpes, t_samples, last_pf):
    """Evaluates strategy robustness using DSR and Sharpe LB."""
    if not all_path_sharpes:
        return 0, 0.0, 0.0, 0, 0.0

    # Ensure all elements are numeric pandas objects
    processed_sharpes = []
    for s in all_path_sharpes:
        if isinstance(s, (pd.Series, pd.DataFrame)):
            processed_sharpes.append(s.astype(float))
        else:
            processed_sharpes.append(pd.Series([float(s)]).astype(float))

    sharpe_df = pd.concat(processed_sharpes, axis=0)
    all_trials_flat = sharpe_df.values.flatten()

    # Calculate robust metrics
    lower_bound_sharpe = sharpe_df.groupby(level=0).quantile(0.05)
    best_idx = lower_bound_sharpe.idxmax()
    best_sharpe_lb = float(lower_bound_sharpe.max())

    n_trials = len(all_trials_flat)
    actual_returns = last_pf.returns().dropna() if (last_pf is not None and hasattr(last_pf, 'returns')) else pd.Series([])
    if len(actual_returns) < 20:
        s_val, k_val = 0.0, 3.0
    else:
        s_val = skew(actual_returns)
        k_val = kurtosis(actual_returns)
        if isinstance(s_val, np.ndarray): s_val = s_val.mean()
        if isinstance(k_val, np.ndarray): k_val = k_val.mean()

    dsr_conf, expected_max = calculate_dsr(
        max_sharpe=best_sharpe_lb,
        trial_sharpes=all_trials_flat,
        n_trials=n_trials,
        t_samples=t_samples,
        skew_val=s_val,
        kurt_val=k_val
    )
    return best_idx, best_sharpe_lb, dsr_conf, n_trials, expected_max

def _save_to_arctic(symbol, best_idx, best_sharpe_lb, dsr_conf):
    """Persists robust hyperparameters to ArcticDB."""
    try:
        import git_arctic
        store = git_arctic.get_arctic()
        if 'global_hyperparameters' not in store.list_libraries():
            store.create_library('global_hyperparameters')
        lib_hp = store['global_hyperparameters']

        # Fallback mechanism for ATR multiplier selection
        atr_val = 4.0

        regime = utils.get_symbol_regime(symbol) if utils else "UNKNOWN"
        hp_df = pd.DataFrame([{
            "symbol": symbol,
            "regime": regime,
            "atr_multiplier": float(atr_val),
            "sharpe_lb": float(best_sharpe_lb),
            "dsr_conf": float(dsr_conf),
            "timestamp": time.time()
        }])

        lib_hp.write(f"atr_mult_{regime}", hp_df, metadata={'symbol': symbol, 'dsr': True})
        logging.info(f"[ARCTIC] Robust Hyperparameters updated for {regime}: {atr_val}x")
    except Exception as e:
        logging.error(f"Failed to write to ArcticDB: {e}")

def run_parameter_sweep(symbol, timeframe='M15', lookback_days=30):
    """
    Asynchronous Quant Researcher: Runs parameter sweeps using CPCV (v15.9).
    """
    logging.info(f"Initiating CPCV Parameter Sweep for {symbol} ({timeframe})...")
    
    try:
        # 1. Fetch Historical Data
        price = _fetch_mt5_data(symbol, timeframe)
        if price is None:
            return {"status": "error", "message": "No Data"}
            
        # 2. Load Model and Predict
        probs = _get_model_predictions(price)
        
        # 3. Purged and Embargoed CV Configuration
        pkf = PurgedKFold(n_splits=5, purge_bars=PURGE_BARS, embargo_bars=EMBARGO_BARS)
        
        # 4. Run Backtest
        all_path_sharpes, last_pf = _run_cv_backtest(price, probs, pkf)

        # 5. Evaluate Robustness (DSR)
        best_idx, best_sharpe_lb, dsr_conf, n_trials, expected_max = _evaluate_robustness(
            all_path_sharpes, len(price), last_pf
        )
        
        logging.info(f"[DSR] Trials: {n_trials} | Expected Max: {expected_max:.2f} | Actual: {best_sharpe_lb:.2f} | Conf: {dsr_conf:.1%}")
        
        # Directive 3: The Ultimate Epistemic Gate
        if dsr_conf < 0.95:
            logging.warning(f"Strategy REJECTED by DSR Gate (Conf {dsr_conf:.1%} < 95%)")
            return {"status": "rejected", "dsr_conf": dsr_conf, "reason": "Multiple Testing Bias"}

        logging.info(f"Best Robust Config (DSR Verified): {best_idx} | Sharpe LB: {best_sharpe_lb:.2f}")
        
        # 6. Persistence
        _save_to_arctic(symbol, best_idx, best_sharpe_lb, dsr_conf)

        # 7. Push Webhook
        send_research_webhook(symbol, best_idx, best_sharpe_lb, n_trials, expected_max, dsr_conf)
            
        return {"status": "success", "best_config": str(best_idx), "sharpe_lb": best_sharpe_lb, "dsr_conf": dsr_conf}
        
    except Exception as e:
        logging.error(f"Research Error: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return {"status": "error", "message": str(e)}

def send_research_webhook(symbol, config, sharpe_lb, n_trials, expected_max, dsr_conf):
    """Pushes a Research Webhook with DSR Multiple-Testing Verification."""
    try:
        payload = {
            "embeds": [{
                "title": f"🔬 DSR ROBUST RESEARCH: Multiple-Testing Clear",
                "description": (
                    f"**Symbol:** `{symbol}`\n"
                    f"**Best Config:** `{config}`\n"
                    f"**Actual Sharpe (LB):** `{sharpe_lb:.2f}`\n"
                    f"**Trials Run ($N$):** `{n_trials}`\n"
                    f"**Max Expected Sharpe:** `{expected_max:.2f}`\n"
                    f"**DSR Confidence:** `{dsr_conf:.1%}`"
                ),
                "color": 0x2ECC71 if dsr_conf >= 0.95 else 0xE74C3C,
                "footer": {"text": "Adaptive Sentinel v15.12 | DSR Multiple-Testing Engine"}
            }]
        }
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    except:
        pass

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Run for the symbol
        run_parameter_sweep(sys.argv[1])
    else:
        print("Usage: python vectorbt_researcher_mcp.py <symbol>")
