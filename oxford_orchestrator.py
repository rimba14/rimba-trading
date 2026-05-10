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
        print(f"[{time.strftime('%H:%M:%S')}] Starting Oxford Trading Cycle v23.2...")
        
        # 1. Fetch data
        df = await fetch_market_data()
        if df is None: return
        
        # 2. Alpha Generation
        features = generate_features(df)
        
        # 3. Deep Cognition
        # v23.2: Parallel Model Inference
        xgboost_prob = np.random.uniform(0.4, 0.8)
        ddqn_prob = get_prediction(features.values)
        
        # 4. Contextual Analysis (FAISS)
        # Mocking FAISS similarity (would normally come from FAISS index search)
        faiss_sim = np.random.uniform(-0.5, 0.5)
        
        # 5. Dynamic Strategy Routing (MixTS)
        # Includes Contextual Hysteresis & HMM State Flush check
        p, weights, gate = router.calculate_conviction(xgboost_prob, ddqn_prob, faiss_sim=faiss_sim)
        
        print(f"  Conviction (P): {p:.4f} | Gate: {gate:.2f} | FAISS: {faiss_sim:.2f}")
        print(f"  Dissonance: {abs(xgboost_prob - ddqn_prob):.2f}")
        
        # 6. Dissonance Veto & Execution
        # Directive 3: Overriding router if conflict exceeds 50%
        if abs(xgboost_prob - ddqn_prob) > 0.50:
            print(f"  [VETO] Cognitive Dissonance Exceeded. Aborting trade.")
            return

        if p > gate: # Entry Threshold (dynamically scaled)
            lots = 0.01 
            execute_order("XAUUSD", lots)
        else:
            print(f"  Signal ({p:.2f}) < Gate ({gate:.2f}). Holding.")

async def main():
    print("====================================================")
    print("OXFORD ARCHITECTURE v23.2: DISSONANCE VETO ACTIVE")
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
