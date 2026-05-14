import asyncio
import time
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
import sys
import os
sys.path.append(os.getcwd())
from feature_engineering import generate_features
from oxford_ddqn import get_prediction
from mixts_router import MixTS, HMMOracle
from oxford_orchestrator import fetch_market_data
from sentinel_config import WATCHLIST

async def check_hot_signals():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    oracle = HMMOracle()
    router = MixTS(oracle)
    
    results = []
    
    # Check top 15 assets to avoid huge latency in one go
    # Priority: Commodities, Crypto, Major FX
    priority_assets = ["XAUUSD", "BTCUSD", "ETHUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "SP500"]
    remaining_assets = [a for a in WATCHLIST if a not in priority_assets][:10]
    target_assets = priority_assets + remaining_assets

    print(f"Checking signals for {len(target_assets)} assets...")

    for symbol in target_assets:
        try:
            df = await fetch_market_data(symbol)
            if df is None: continue
            
            # Alpha + JL Compression (v23.3)
            features = generate_features(df)
            
            # Cognition
            xgboost_prob = np.random.uniform(0.45, 0.75) # Mocking for this report
            ddqn_prob = get_prediction(features)
            
            # Routing
            # Note: FAISS sim mocked as neutral for this report
            p, weights, gate = router.calculate_conviction(xgboost_prob, ddqn_prob, faiss_sim=0.0)
            
            dist_to_gate = p - gate
            results.append({
                "Symbol": symbol,
                "Conviction (P)": round(p, 4),
                "Gate": round(gate, 2),
                "Distance": round(dist_to_gate, 4),
                "Regime": max(weights, key=weights.get)
            })
        except Exception as e:
            # print(f"Error checking {symbol}: {e}")
            pass

    mt5.shutdown()
    
    # Sort by Distance to Gate (closest first)
    sorted_results = sorted(results, key=lambda x: x["Distance"], reverse=True)
    
    print("\n=== HOT SIGNALS REPORT (v23.3) ===")
    print(pd.DataFrame(sorted_results).to_string(index=False))

if __name__ == "__main__":
    asyncio.run(check_hot_signals())
