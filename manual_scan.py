import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import gitagent_synthesis as syn
import gitagent_transformer as trans
import gitagent_microstructure as micro
import json
import os
from datetime import datetime, timezone

def rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

# Watchlist
symbols = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NAS100", "SP500", "XAUUSD+", "CL-OIL", "BTCUSD", "ETHUSD", "SOLUSD"
]

if not mt5.initialize():
    print("MT5 Init Failed")
    quit()

print(f"--- NEURAL MARKET SCAN | {datetime.now(timezone.utc)} ---")

# 1. Account Audit
acc = mt5.account_info()
pos = mt5.positions_get()
thesis_file = "C:\\Sentinel_Project\\\position_thesis.json"
thesis_data = {}
if os.path.exists(thesis_file):
    with open(thesis_file, 'r') as f:
        data = json.load(f)
        thesis_data = {str(k): v for k, v in data.items()}

print(f"Balance: ${acc.balance} | Equity: ${acc.equity} | Margin: {acc.margin_level:.1f}%")
print(f"Active Positions: {len(pos) if pos else 0}")

# 2. Ensemble Scan
results = []
for sym in symbols:
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 100)
    if rates is None or len(rates) < 50: continue
    df = pd.DataFrame(rates)
    
    price = df['close'].iloc[-1]
    sma50 = df['close'].rolling(50).mean().iloc[-1]
    sma200 = df['close'].rolling(200).mean().iloc[-1]
    r = rsi(df['close']).iloc[-1]
    
    wy_b = 0.4 if price > sma50 and price > sma200 else 0.1
    smc_b = 0.3 if price > sma50 and r < 40 else 0.1
    
    vol = df['tick_volume'].iloc[-1]
    vol_sma = df['tick_volume'].rolling(20).mean().iloc[-1]
    vol_ratio = vol / vol_sma if vol_sma > 0 else 1.0
    whl_b = 0.5 * vol_ratio if vol_ratio > 2.0 and df['close'].iloc[-1] > df['close'].iloc[-2] else 0.0
    
    trans_score = trans.get_transformer_score(df.tail(100))
    lq_score = micro.get_microstructure_score(df)
    
    agent_scores = {
        "W": (r-50)/50.0, "Wy": wy_b, "SMC": smc_b,
        "WHL": whl_b, "TRANS": trans_score, "MICRO": (lq_score-50)/50.0
    }
    features = syn.extract_features(agent_scores, macro_data={'cosmic': {'alignment': 0.1}})
    score = syn.monolithic_score(syn.kernel_transform(features), bayes_weights={})
    
    results.append({"symbol": sym, "score": score, "rsi": r, "lq": lq_score})

df_res = pd.DataFrame(results).sort_values(by='score', ascending=False)
print("\n--- TOP NEURAL OPPORTUNITIES ---")
print(df_res.head(10))

mt5.shutdown()
