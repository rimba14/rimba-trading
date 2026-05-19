import os
import sys
try:
    import torch
except ImportError:
    torch = None
except OSError:
    print("[TIMESFM] Torch DLL failure. Oracle offline.")
    torch = None

import numpy as np
import pandas as pd
import json
import time
from typing import Tuple, Dict

# Performance Optimization
if torch and torch.cuda.is_available():
    torch.set_float32_matmul_precision("high")

# Inject the local TimesFM library
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    if torch:
        from timesfm_internal.timesfm_2p5.timesfm_2p5_torch import TimesFM_2p5_200M_torch
        from timesfm_internal.configs import ForecastConfig
    else:
        TimesFM_2p5_200M_torch = None
        ForecastConfig = None
except ImportError:
    TimesFM_2p5_200M_torch = None
    ForecastConfig = None

# Configuration
import sys
sys.path.append("C:/Sentinel_Project")
import git_arctic
import gitagent_utils as utils
CACHE_LIB = "oracle_cache"
MODEL_PATH = "google/timesfm-2.5-200m-pytorch"
TEMPERATURE = 2.5 # Calibrated temperature constant

import gc
if torch:
    torch.set_num_threads(4)

_MODEL = None
QUANT_PATH = "C:/Sentinel_Project/data/timesfm_quantized.pt"

def init_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
        
    if TimesFM_2p5_200M_torch is None:
        return None

    try:
        # Directive 3: Hard-Lock the Bridge Loader
        # Ensure file exists and is greater than 1MB (1,000,000 bytes)
        if not os.path.exists(QUANT_PATH) or os.path.getsize(QUANT_PATH) < 1000000:
            raise FileNotFoundError(f"TimesFM artifact missing at {QUANT_PATH}")

        print(f"[TIMESFM] Loading Pre-Quantized Model from {QUANT_PATH}...")
        _MODEL = torch.load(QUANT_PATH, weights_only=False)
        
        # Directive 1: Oracle Dependency Compile (v28.21 SRE)
        # Dynamically compile the model to reconstruct compiled_decode in memory post-load
        if hasattr(_MODEL, 'compile') and ForecastConfig is not None:
            config = ForecastConfig(
                max_context=1024,
                max_horizon=48,
                normalize_inputs=True,
                use_continuous_quantile_head=True
            )
            _MODEL.compile(config)
            print("[TIMESFM] Model compiled successfully post-load.")
        
        # Directive 3: TurboQuant (v23.3 Omni-Compression)
        # Enable 4-bit KV cache quantization and subquadratic attention strategy
        if hasattr(_MODEL, 'enable_turboquant'):
            _MODEL.enable_turboquant(kv_cache_bits=4, attention_mode="subquadratic")
            print("[TIMESFM] TurboQuant KV Cache (4-bit) Enabled.")
        
        print("[TIMESFM] Pre-Quantized Model Loaded Successfully.")
        print("[TIMESFM] Oracle Operational (Q4.12 Optimized).")
    except Exception as e:
        print(f"[TIMESFM] CRITICAL: Model Loading Failed: {e}")
        import traceback
        print(traceback.format_exc())
        raise Exception(f"Failed to load TimesFM model: {e}")
    return _MODEL

def update_risk_cache(symbol: str, ohlcv_df: pd.DataFrame):
    """
    Computes P10/P90 boundaries and saves to cache.
    ohlcv_df should have at least 512 bars of M15 data.
    """
    try:
        model = init_model()
        if model is None:
            return
        
        # Prepare inputs (close prices)
        if len(ohlcv_df) < 32:
            print(f"[TIMESFM] Insufficient data for {symbol}: {len(ohlcv_df)} bars")
            return
            
        # Directive 2: Robust Input Normalization (Z-Score)
        close_raw = ohlcv_df['close'].values.astype(np.float32)
        mean_val = np.mean(close_raw)
        std_val = np.std(close_raw) + 1e-9
        close_prices = (close_raw - mean_val) / std_val
        
        # Directive 1: Strict Input Normalization (v18.7)
        # Bounding to [-5.0, 5.0] to prevent Q4.12 fixed-point clipping at 7.99
        close_prices = np.clip(close_prices, -5.0, 5.0)
        
        # Inference
        print(f"[TIMESFM] Running inference for {symbol} (Input Normalized)...")
        point, quantiles = model.forecast(
            horizon=48,
            inputs=[close_prices]
        )
        
        # Extract P10/P90 for the 12-hour horizon and DE-NORMALIZE
        # Directive 3: Restore to Price-Space
        p10_norm = float(quantiles[0, 0, 1])
        p90_norm = float(quantiles[0, 0, 9])
        
        p10 = (p10_norm * std_val) + mean_val
        p90 = (p90_norm * std_val) + mean_val
        
        # Update ArcticDB Cache
        store = git_arctic.get_arctic()
        df_cache = pd.DataFrame([{
            "p10": p10,
            "p90": p90,
            "timestamp": utils.get_utc_epoch(),
            "last_price": float(close_prices[-1])
        }])
        
        # Write to ArcticDB (Standard version-replacement write)
        store['oracle_cache'].write(f"{symbol}_timesfm", df_cache)
        
        print(f"[TIMESFM] ArcticDB cache updated for {symbol}: P10={p10:.5f}, P90={p90:.5f}")
        
    except Exception as e:
        # Directive 2: Graceful Degradation (v28.21 SRE)
        print(f"[ORACLE_DEGRADED] TimesFM failed for {symbol}: {e}")

def get_cached_boundaries(symbol: str) -> Tuple[float, float]:
    """
    Returns (p10, p90) from cache if valid. Returns (None, None) if stale or missing.
    """
    try:
        store = git_arctic.get_arctic()
        item = store['oracle_cache'].read(f"{symbol}_timesfm")
        
        if item is not None:
            data = item.data.iloc[-1] # Get latest row
            # Check if cache is older than 15 minutes
            if utils.get_utc_epoch() - data['timestamp'] < 900:
                return float(data['p10']), float(data['p90'])
                
    except Exception as e:
        print(f"[TIMESFM] ArcticDB Read Error for {symbol}: {e}")
        
    return None, None

if __name__ == "__main__":
    # Test update with synthetic data
    print("[TEST] Initializing synthetic test...")
    test_df = pd.DataFrame({'close': np.random.normal(1.10, 0.001, 512)})
    update_risk_cache("EURUSD", test_df)
    p10, p90 = get_cached_boundaries("EURUSD")
    print(f"[TEST] Cached Boundaries: P10={p10}, P90={p90}")
