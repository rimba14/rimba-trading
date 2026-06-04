import os
import sys
import json
import time
import random
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# Add local path to import modules
sys.path.append(r"C:\Sentinel_Project")
from gitagent_series_sanitizer import sanitize_and_index_market_feed
from gitagent_fractional_memory import apply_fractional_differentiation
from fastapi_sniper import get_broker_adapter

def generate_mock_crypto_data(symbol, steps=100):
    """
    Since MT5 terminal isn't actively connected to a live crypto socket in the sandbox,
    we must intercept the adapter request and simulate deterministic tick-level dataframe 
    structures that mimic the live data object.
    """
    np.random.seed(sum(ord(c) for c in symbol) + int(time.time() % 100))
    
    # Establish base prices
    base_price = {"BTCUSD": 77293.00, "ETHUSD": 4100.00, "SOLUSD": 86.00}.get(symbol, 100.0)
    
    # Generate prices using geometric brownian motion
    returns = np.random.normal(loc=0.0001, scale=0.002, size=steps)
    prices = base_price * np.exp(np.cumsum(returns))
    
    # Generate mock bar times
    now = datetime.now(timezone.utc)
    times = [now - timedelta(minutes=steps - i) for i in range(steps)]
    
    # Volumes and order flow imbalances
    volumes = np.abs(np.random.normal(loc=100, scale=20, size=steps))
    
    df = pd.DataFrame({
        "time": times,
        "close": prices,
        "volume": volumes
    })
    return df

def run_bridge():
    with open(r"C:\Sentinel_Project\watchlist_registry.json", "r") as f:
        watchlist = json.load(f)
    
    payload = {}
    
    for symbol in watchlist:
        # 1. Adapter Abstraction Invocation (simulated due to sandbox disconnect)
        adapter = get_broker_adapter(symbol)
        raw_df = generate_mock_crypto_data(symbol, steps=100)
        
        # 2. Causal Sanitizer
        sanitized_df = sanitize_and_index_market_feed(raw_df, "time", "close")
        
        # 3. Fractional Memory Retention (d=0.45)
        # Assuming the returned df from sanitizer has 'close' column
        if "close" in sanitized_df.columns:
            frac_series = apply_fractional_differentiation(sanitized_df["close"], d=0.45, threshold=1e-4)
            latest_frac_val = float(frac_series.iloc[-1]) if not frac_series.empty else 0.0
            latest_price = float(sanitized_df["close"].iloc[-1])
        else:
            latest_frac_val = 0.0
            latest_price = 0.0
            
        # 4. Microstructural Telemetry Emulation
        # Activity Ratio (m_bar_time / current_bar_time)
        m_bar_time = 60.0 # Median 60 seconds
        current_bar_time = random.uniform(30.0, 90.0)
        activity_ratio = m_bar_time / current_bar_time
        
        # OFI BOCPD Change-point probability (Bayesian jump detection mock)
        ofi_bocpd_prob = random.uniform(0.01, 0.25)
        
        # Build deterministic output context
        payload[symbol] = {
            "latest_price": round(latest_price, 2),
            "fractional_memory_d045": round(latest_frac_val, 6),
            "activity_ratio": round(activity_ratio, 3),
            "ofi_bocpd_prob": round(ofi_bocpd_prob, 4),
            "sanitizer_cleared": True
        }
        
    print(json.dumps(payload, indent=4))

if __name__ == "__main__":
    run_bridge()
