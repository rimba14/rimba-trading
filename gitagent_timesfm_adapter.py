# Sentinel TimesFM 2.5 Adapter (Python 3.14 Manual Port)
# Replaces bespoke neural estimators with Foundation Model Edge detection.

import sys
import os
try:
    import torch
except (ImportError, OSError):
    torch = None
import numpy as np
import pandas as pd
from typing import Tuple

# Inject the local TimesFM library
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    if torch:
        from timesfm_internal.timesfm_2p5.timesfm_2p5_torch import TimesFM_2p5_200M_torch
        from timesfm_internal.configs import ForecastConfig
    else:
        TimesFM_2p5_200M_torch = None
        ForecastConfig = None
except (ImportError, OSError):
    TimesFM_2p5_200M_torch = None
    ForecastConfig = None

# Singleton Cache for Model Weights
_CACHED_TFM = None

def get_tfm_edge(ohlcv_df: pd.DataFrame, horizon: int = 12) -> Tuple[float, float]:
    """
    Computes Foundation Model Edge and Direction volatility spread.
    Returns: (tfm_edge, tfm_dir)
    tfm_edge: Normalized volatility spread (quantiles vs current price).
    tfm_dir: Forecasted trajectory direction (-1.0 to 1.0).
    """
    global _CACHED_TFM
    
    try:
        # 1. Initialize Model (Lazy-load)
        if _CACHED_TFM is None and TimesFM_2p5_200M_torch is not None:
            print("[TFM] Initializing Foundation Model (200M)...")
            _CACHED_TFM = TimesFM_2p5_200M_torch(torch_compile=False) # Disable compile for first load
            # Weights are downloaded via HF Hub mixin automatically on first run
            _CACHED_TFM = _CACHED_TFM.from_pretrained("google/timesfm-2.5-200m-pytorch")
            
            _CACHED_TFM.compile(ForecastConfig(
                max_context=512, # Optimized for trading window
                max_horizon=horizon,
                normalize_inputs=True,
                use_continuous_quantile_head=True
            ))
            print("[TFM] Foundation Model Ready.")

        # 2. Preprocessing
        # We use 'close' prices for the 1-D forecast required by TimesFM
        close_prices = ohlcv_df['close'].values.astype(np.float32)
        
        # 3. Inference
        point, quantiles = _CACHED_TFM.forecast(
            horizon=horizon,
            inputs=[close_prices]
        )
        
        # 4. Feature Extraction
        current_price = close_prices[-1]
        forecast_median = point[0, -1] # Final point in horizon median
        p10 = quantiles[0, -1, 1]      # Final point 10th percentile
        p90 = quantiles[0, -1, 9]      # Final point 90th percentile
        
        # TFM_DIR: Distance from current price to median, normalized
        tfm_dir = (forecast_median - current_price) / (current_price * 0.001 + 1e-9)
        tfm_dir = np.clip(tfm_dir, -1.0, 1.0)
        
        # TFM_EDGE: Volatility Spread.
        vol_spread = p90 - p10
        edge_bias = (forecast_median - current_price) / (vol_spread + 1e-9)
        tfm_edge = np.clip(edge_bias * 5.0, -5.0, 5.0) 
        
        return float(tfm_edge), float(tfm_dir)

    except Exception as e:
        print(f"[TFM] Adapter Error: {e}")
        return 0.0, 0.0

if __name__ == "__main__":
    # Unit Test with Regimes
    print("Testing TimesFM Adapter (BULLISH REGIME)...")
    bull_data = pd.DataFrame({'close': np.linspace(10, 15, 200)}) # Uptrend
    edge, direction = get_tfm_edge(bull_data)
    print(f"BULL Result -> Edge: {edge:.4f}, Dir: {direction:.4f}")

    print("\nTesting TimesFM Adapter (BEARISH REGIME)...")
    bear_data = pd.DataFrame({'close': np.linspace(15, 10, 200)}) # Downtrend
    edge, direction = get_tfm_edge(bear_data)
    print(f"BEAR Result -> Edge: {edge:.4f}, Dir: {direction:.4f}")

    print("\nTesting TimesFM Adapter (FLAT REGIME)...")
    flat_data = pd.DataFrame({'close': np.ones(200) * 10.0}) # No move
    edge, direction = get_tfm_edge(flat_data)
    print(f"FLAT Result -> Edge: {edge:.4f}, Dir: {direction:.4f}")
