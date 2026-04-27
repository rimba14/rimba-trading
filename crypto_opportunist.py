import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import os
from gitagent_synthesis import extract_features
from gitagent_memory_fast import FastMemory
from gitagent_groq_lpu import GroqReasoningEngine

# ─── SETUP ───
CRYPTO_SYMBOLS = ["BTCUSD", "ETHUSD", "SOLUSD", "ADAUSD", "XRPUSD"]
TIMEFRAME = mt5.TIMEFRAME_M15

def get_live_opportunist_report():
    if not mt5.initialize():
        print("MT5 Initialization Failed")
        return
    
    memory = FastMemory(dim=89)
    groq_engine = GroqReasoningEngine(model_name="llama-3.1-8b-instant")
    
    reports = []
    print("\n[OPPORTUNIST] Scanning Crypto Markets...")
    
    for sym in CRYPTO_SYMBOLS:
        rates = mt5.copy_rates_from_pos(sym, TIMEFRAME, 0, 150)
        if rates is None or len(rates) < 128:
            print(f"  - Skip {sym}: Insufficient history.")
            continue
            
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # 1. Feature Extraction (89-dim)
        # Note: mocking some status/lob data for the scan
        features_dict = extract_features(
            agent_scores={}, 
            ohlcv_df=df, 
            agent_status={"inventory": 0.0, "unreal_pnl": 0.0},
            lob_data={"vpin": 0.1, "spread_norm": 0.01}
        )
        
        # Convert dict to vector (this assumes alphabetically sorted keys match training)
        sorted_keys = sorted([k for k in features_dict.keys() if not k.startswith('_')])
        vector = np.array([features_dict[k] for k in sorted_keys]).astype('float32')
        
        if vector.shape[0] != memory.dim:
            print(f"  - Fix {sym}: Found dim {vector.shape[0]} but expected {memory.dim}. Padding/Trimming...")
            if vector.shape[0] > memory.dim:
                vector = vector[:memory.dim]
            else:
                vector = np.pad(vector, (0, memory.dim - vector.shape[0]))

        # 2. Memory Retrieval
        try:
            history = memory.retrieve(vector, k=2)
        except Exception as e:
            print(f"  - Memory error {sym}: {e}")
            history = []
        
        # 3. Groq Reasoning
        summary = f"{sym} M15: Close {df['close'].iloc[-1]:.2f}, Volatility high, Anomaly score {features_dict.get('_anomaly_score', 0):.2f}"
        reasoning = groq_engine.analyze_regime(summary, history)
        
        reports.append({
            "Symbol": sym,
            "Price": df['close'].iloc[-1],
            "Reasoning": reasoning
        })
    
    with open("C:\\Sentinel_Project\\crypto_report.txt", "w") as f_out:
        f_out.write("SENTINEL v13.5 CRYPTO OPPORTUNIST REPORT\n")
        f_out.write("="*40 + "\n")
        for r in reports:
            line = f"\n[{r['Symbol']}] @ {r['Price']:.2f}\n  THESIS: {r['Reasoning']}\n"
            print(line)
            f_out.write(line)
        f_out.write("\n" + "="*40 + "\n")

    mt5.shutdown()
    return reports

if __name__ == "__main__":
    results = get_live_opportunist_report()
    if results:
        print("\n" + "="*80)
        print(" SENTINEL v13.5 CRYPTO OPPORTUNIST REPORT ")
        print("="*80)
        for r in results:
            print(f"\n[{r['Symbol']}] @ {r['Price']:.2f}")
            print(f"  THESIS: {r['Reasoning']}")
        print("="*80)
