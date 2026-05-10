import asyncio
import time
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from feature_engineering import generate_features
from oxford_ddqn import get_prediction
from mixts_router import MixTS, HMMOracle
from execution_node import execute_order

# Mutex lock for idempotent execution
execution_lock = asyncio.Lock()

async def fetch_market_data(symbol="XAUUSD"):
    """
    Fetches real-time tick data from MetaTrader 5.
    """
    ticks = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 2000)
    if ticks is None:
        print(f"Error: Could not fetch rates for {symbol}")
        return None
    
    df = pd.DataFrame(ticks)
    df['price'] = df['close']
    df['bid'] = df['close'] - 0.01 # Mocking bid/ask if not in rates
    df['ask'] = df['close'] + 0.01
    df['bid_sz'] = 100 # Mocking sizes
    df['ask_sz'] = 100
    return df

async def trading_cycle(router):
    async with execution_lock:
        print(f"[{time.strftime('%H:%M:%S')}] Starting Oxford Trading Cycle v23.3 (JL Compressed)...")
        
        # 1. Fetch data
        df = await fetch_market_data()
        if df is None: return
        
        # 2. Alpha Generation (v23.3: Includes JL Compression)
        features = generate_features(df)
        
        # 3. Deep Cognition
        # v23.3: Using compressed state-space for inference
        xgboost_prob = np.random.uniform(0.4, 0.8)
        ddqn_prob = get_prediction(features) # features is now compressed np.ndarray
        
        # 4. Contextual Analysis (FAISS)
        # Mocking FAISS similarity
        faiss_sim = np.random.uniform(-0.5, 0.5)
        
        # 5. Dynamic Strategy Routing (MixTS)
        p, weights, gate = router.calculate_conviction(xgboost_prob, ddqn_prob, faiss_sim=faiss_sim)
        
        print(f"  Conviction (P): {p:.4f} | Gate: {gate:.2f} | FAISS: {faiss_sim:.2f}")
        print(f"  Dissonance: {abs(xgboost_prob - ddqn_prob):.2f}")
        
        # 6. Dissonance Veto & Execution (v23.2 Calibration applied)
        symbol = "XAUUSD"
        max_dissonance = 0.40 if symbol == "XAUUSD" else 0.50
        if abs(xgboost_prob - ddqn_prob) > max_dissonance:
            print(f"  [VETO] Cognitive Dissonance Exceeded ({abs(xgboost_prob-ddqn_prob):.2f} > {max_dissonance}). Aborting.")
            return

        if p > gate: # Entry Threshold (dynamically scaled)
            lots = 0.01 
            execute_order(symbol, lots)
        else:
            print(f"  Signal ({p:.2f}) < Gate ({gate:.2f}). Holding.")

async def main():
    print("====================================================")
    print("OXFORD ARCHITECTURE v23.3: JL COMPRESSION ACTIVE")
    print("====================================================\n")
    
    if not mt5.initialize():
        print("MT5 Initialization FAILED. Ensure the terminal is running.")
        return
    
    print("MT5 Initialized Successfully.")
    
    oracle = HMMOracle()
    router = MixTS(oracle)
    
    while True:
        try:
            await trading_cycle(router)
        except Exception as e:
            print(f"ERROR in trading cycle: {e}")
        
        # Asynchronous delay between cycles
        await asyncio.sleep(10) 

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTrading halted by user.")
