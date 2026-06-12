import os
import sys
import time
import json
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import MetaTrader5 as mt5
from scipy.stats import wasserstein_distance

# Add paths to make sure we can import other gitagent modules if needed
sys.path.append(r"C:\Users\ADMIN\.antigravity\rimba-trading")
sys.path.append(r"C:\Sentinel_Project")

import gitagent_timesnet as tnet
import sentinel_config as cfg

# Define output path
STATE_DIR = r"C:\Sentinel_Project\data"
if not os.path.exists(STATE_DIR):
    STATE_DIR = r"C:\Users\ADMIN\.antigravity\rimba-trading\data"
os.makedirs(STATE_DIR, exist_ok=True)
STATE_FILE = os.path.join(STATE_DIR, "timesnet_state.json")

def main():
    if not mt5.initialize():
        print("[TIMESNET_ERR] MT5 initialization failed.")
        sys.exit(1)
        
    watchlist = cfg.WATCHLIST
    results = {}
    
    # Instantiate TimesNet model
    model = tnet.TimesNetPerception(enc_in=5, d_model=64, top_k=3, seq_len=128)
    model.eval()
    
    for symbol in watchlist:
        try:
            # Copy rates
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 128)
            if rates is None or len(rates) < 128:
                continue
                
            df = pd.DataFrame(rates)
            data = df[['open', 'high', 'low', 'close', 'tick_volume']].values
            data_norm = (data - np.mean(data, axis=0)) / (np.std(data, axis=0) + 1e-9)
            
            x = torch.FloatTensor(data_norm).unsqueeze(0)
            with torch.no_grad():
                features, anomaly_tensor, reconstructed = model(x)
                anomaly_score = float(anomaly_tensor.cpu().item())
                
            # Compute Wasserstein distance on returns against stylized standard normal
            close_prices = df['close'].values
            returns = np.diff(close_prices) / (close_prices[:-1] + 1e-9)
            std_ret = np.std(returns) if np.std(returns) > 1e-9 else 0.001
            normal_dist = np.random.normal(0, std_ret, len(returns))
            w_dist = float(wasserstein_distance(np.sort(returns), np.sort(normal_dist)))
            
            # Formulate confidence vector [pass_confidence, anomaly_confidence]
            fail_conf = min(1.0, max(0.0, anomaly_score * 5.0))
            pass_conf = 1.0 - fail_conf
            
            # Epistemic pass
            epistemic_pass = bool(w_dist < 0.65)
            
            results[symbol] = {
                "timestamp": int(time.time()),
                "source_oracle": "TIMESNET",
                "confidence_vector": [pass_conf, fail_conf],
                "wasserstein_distance": w_dist,
                "epistemic_pass": epistemic_pass
            }
        except Exception as e:
            print(f"[TIMESNET_ERR] Error processing {symbol}: {e}")
            
    mt5.shutdown()
    
    # Atomic write to JSON
    temp_file = STATE_FILE + ".tmp"
    with open(temp_file, "w") as f:
        json.dump(results, f, indent=2)
    os.replace(temp_file, STATE_FILE)
    print(f"[TIMESNET] Successfully wrote states for {len(results)} assets.")

if __name__ == "__main__":
    main()
