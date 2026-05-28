import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime
import gitagent_synthesis as syn
import gitagent_transformer as trans
import gitagent_ppo as ppo
import gitagent_microstructure as micro

symbols = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD",
    "NAS100.r", "SP500.r", "DJ30.r", "GER40.r",
    "XAUUSD+", "CL-OIL",
    "NVIDIA", "AAPL", "MSFT", "META", "TSLA",
    "BTCUSD", "ETHUSD", "SOLUSD"
]

if not mt5.initialize():
    print("MT5 Initialization Failed")
    quit()

OVERNIGHT_THRESHOLD = 62

results = []
for sym in symbols:
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 100)
    if rates is None or len(rates) < 50: continue
    df = pd.DataFrame(rates)
    
    # 1. Monolithic Score (Real logic roughly approximated)
    lq_score = micro.get_microstructure_score(df)
    trans_score = trans.get_transformer_score(df.tail(100))
    
    # Mock some agent features for diagnostic
    agent_scores = {
        "W": 0.1, "Wy": 0.2, "SMC": 0.1, "RPB": 0.2, 
        "LLM": 0.0, "WHL": 0.0, "SEN": 0.0, 
        "TRANS": trans_score,
        "MICRO": (lq_score - 50) / 50.0
    }
    
    features = syn.extract_features(agent_scores, macro_data={'cosmic': {'ap':12, 'lunar_value':0}})
    kernel = syn.kernel_transform(features)
    mono_score = syn.monolithic_score(kernel, bayes_weights={})
    
    # 2. EDGE Calculation (Component breakdown)
    edge_agents = abs(mono_score) * 0.4
    edge_sigq = 15.0 # baseline
    edge_hurst = 7.0 # baseline
    edge_fp = 5.0 # baseline
    edge_ising = 5.0 # baseline
    edge_fractal = 3.0 # baseline
    edge_vix = 4.0 # baseline
    
    total_edge = edge_agents + edge_sigq + edge_hurst + edge_fp + edge_ising + edge_fractal + edge_vix
    
    results.append({
        "Symbol": sym,
        "MonoScore": round(mono_score, 1),
        "EdgePerc": round(total_edge, 1),
        "Status": "PASS" if total_edge >= OVERNIGHT_THRESHOLD else f"FAIL (Needs {OVERNIGHT_THRESHOLD-total_edge:.1f} more)"
    })

df_res = pd.DataFrame(results)
print("\n--- DIAGNOSTIC: WHY NO TRADES? ---")
print(df_res.to_string(index=False))

mt5.shutdown()
