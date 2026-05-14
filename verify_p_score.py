import asyncio
import sys
sys.path.append(r"C:\Sentinel_Project")
from oxford_orchestrator import fetch_market_data, MixTS, HMMOracle, generate_features, get_prediction
import numpy as np
import MetaTrader5 as mt5

async def test_p():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return
    
    df = await fetch_market_data("XAUUSD")
    if df is None: return
    
    features = generate_features(df)
    xgboost_prob = np.random.uniform(0.4, 0.8)
    ddqn_prob = get_prediction(features)
    
    oracle = HMMOracle()
    router = MixTS(oracle)
    p, weights, gate = router.calculate_conviction(xgboost_prob, ddqn_prob, faiss_sim=0.0)
    
    print(f"VERIFICATION_RESULT: P={p:.8f}")
    mt5.shutdown()

if __name__ == "__main__":
    asyncio.run(test_p())
