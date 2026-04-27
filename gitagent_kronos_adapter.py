import sys
import os
import torch
import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any

# Inject the local Kronos library
KRONOS_REPO_PATH = "C:\\Sentinel_Project\\kronos_repo"
if KRONOS_REPO_PATH not in sys.path:
    sys.path.append(KRONOS_REPO_PATH)

from model import Kronos, KronosTokenizer, KronosPredictor

# Singleton Cache for Model Weights
_CACHED_KRONOS = None

def get_kronos_forecast(ohlcv_df: pd.DataFrame, horizon: int = 12) -> Dict[str, Any]:
    """
    Computes Foundation Model Forecast using Kronos.
    Returns: Dict containing 'forecast_p50', 'forecast_p90', 'forecast_p10', 'kronos_bias'
    """
    global _CACHED_KRONOS
    
    try:
        # 1. Initialize Model (Lazy-load)
        if _CACHED_KRONOS is None:
            print("[KRONOS] Initializing Foundation Model (Kronos-small)...")
            tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
            model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
            _CACHED_KRONOS = KronosPredictor(model, tokenizer, max_context=512)
            print("[KRONOS] Foundation Model Ready.")

        # 2. Preprocessing
        # Kronos requires 'open', 'high', 'low', 'close', 'volume', 'amount'
        # We ensure they exist or fill with zeros
        required_cols = ['open', 'high', 'low', 'close']
        for col in required_cols:
            if col not in ohlcv_df.columns:
                raise ValueError(f"Missing column {col} in input DataFrame")
        
        if 'volume' not in ohlcv_df.columns:
            ohlcv_df['volume'] = 0.0
        if 'amount' not in ohlcv_df.columns:
            ohlcv_df['amount'] = ohlcv_df['close'] * ohlcv_df['volume']

        # 3. Timestamps
        if 'time' in ohlcv_df.columns:
            x_timestamp = pd.to_datetime(ohlcv_df['time'])
        else:
            x_timestamp = pd.to_datetime(np.arange(len(ohlcv_df)), unit='h') # Mocked
            
        # Create future timestamps (mocked sequence)
        last_time = x_timestamp.iloc[-1]
        y_timestamp = pd.date_range(start=last_time + pd.Timedelta(minutes=5), periods=horizon, freq='5min')
        
        # 4. Inference
        pred_df = _CACHED_KRONOS.predict(
            df=ohlcv_df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=horizon,
            sample_count=5 # Ensemble for better stability
        )
        
        # 5. Feature Extraction
        current_price = ohlcv_df['close'].iloc[-1]
        forecast_p50 = pred_df['close'].iloc[-1] # End of horizon
        
        # Simple Bias
        change = (forecast_p50 / current_price) - 1.0
        kronos_bias = np.tanh(change * 20.0) # Scaled for -1 to 1
        
        return {
            "p50": float(forecast_p50),
            "bias": float(kronos_bias),
            "change_pct": float(change),
            "forecast_df": pred_df,
            "status": "success"
        }

    except Exception as e:
        print(f"[KRONOS] Adapter Error: {e}")
        return {"status": "error", "message": str(e), "bias": 0.0}

if __name__ == "__main__":
    # Unit Test
    print("Testing Kronos Adapter...")
    mock_data = pd.DataFrame({
        'open': np.linspace(10, 15, 100),
        'high': np.linspace(11, 16, 100),
        'low': np.linspace(9, 14, 100),
        'close': np.linspace(10, 15, 100),
        'volume': np.random.rand(100) * 1000
    })
    result = get_kronos_forecast(mock_data)
    print(f"Result -> Bias: {result.get('bias', 0):.4f}, Status: {result.get('status')}")
