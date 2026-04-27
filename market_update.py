import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime
import gitagent_synthesis as syn
import gitagent_transformer as trans
import gitagent_ppo as ppo

# Configuration for the scan
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

def get_live_vix():
    return 21.5 # Fixed proxy for speed in this one-off report

results = []
for sym in symbols:
    # print(f"Scanning {sym}...")
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 100)
    if rates is None or len(rates) < 50: continue
    df = pd.DataFrame(rates)
    
    # Calculate indicators
    chg = ((df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2]) * 100
    
    def rsi_func(series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-9)
        return 100 - (100 / (1 + rs))
    
    r = rsi_func(df['close']).iloc[-1]

    # Calculate agent consensus features
    # (Mocking agent_scores based on price action for the demo report)
    agent_scores = {
        "W": 0.5 if r < 30 else -0.5 if r > 70 else 0,
        "Wy": 0.3 if chg > 0 else -0.3,
        "SMC": 0.4 if chg > 0 else -0.4,
        "RPB": 0.2, "LLM": 0.3, "WHL": 0.1, "SEN": 0.2, "TRANS": 0.1, "MICRO": 0.5
    }
    
    cosmic_data = {'ap': 12, 'lunar_value': 0.1}
    features = syn.extract_features(agent_scores, macro_data={'cosmic': cosmic_data})
    kernel = syn.kernel_transform(features)
    score = syn.monolithic_score(kernel, bayes_weights={})
    
    # PPO Observation
    ppo_state = [agent_scores['W'], agent_scores['Wy'], agent_scores['SMC'], 0.1, (r-50)/50.0, chg, 0.5]
    ppo_action, ppo_probs = ppo.get_ppo_action(ppo_state)
    sig = "HOLD" if ppo_action == 0 else "BUY" if ppo_action == 1 else "SELL"
    
    results.append({
        "Symbol": sym,
        "Price": df['close'].iloc[-1],
        "Change%": round(chg, 2),
        "MonoScore": round(score, 1),
        "PPO_Signal": sig,
        "PPO_Conf": round(max(ppo_probs) * 100, 1)
    })

df_res = pd.DataFrame(results)
# Sort by confidence
df_res.sort_values(by="PPO_Conf", ascending=False, inplace=True)

print("\n--- MARKET INTELLIGENCE UPDATE (v9.5) ---")
print(f"Timestamp: {datetime.now().strftime('%H:%M:%S')}")
print(df_res.head(15).to_string(index=False))

mt5.shutdown()
