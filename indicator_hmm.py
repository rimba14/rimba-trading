import os
import sys
import time
import json
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

# Add paths to make sure we can import other gitagent modules if needed
sys.path.append(r"C:\Users\ADMIN\.antigravity\rimba-trading")
sys.path.append(r"C:\Sentinel_Project")

import gitagent_hmm
from wasserstein_regime_cluster import WassersteinRegimeCluster
import sentinel_config as cfg

# Define output path
STATE_DIR = r"C:\Sentinel_Project\data"
if not os.path.exists(STATE_DIR):
    STATE_DIR = r"C:\Users\ADMIN\.antigravity\rimba-trading\data"
os.makedirs(STATE_DIR, exist_ok=True)
STATE_FILE = os.path.join(STATE_DIR, "hmm_state.json")

def main():
    if not mt5.initialize():
        print("[HMM_ERR] MT5 initialization failed.")
        sys.exit(1)
        
    watchlist = cfg.WATCHLIST
    results = {}
    
    # Initialize the Wasserstein Optimal Transport clusterer
    clusterer = WassersteinRegimeCluster(window_size=50, n_clusters=3)
    
    for symbol in watchlist:
        try:
            # Copy rates
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 200)
            if rates is None or len(rates) < 100:
                continue
                
            df = pd.DataFrame(rates)
            close_prices = df['close'].values
            
            # 1. HMM regime
            hmm_state, hmm_prob, hmm_probs = gitagent_hmm.get_current_state(close_prices)
            
            # 2. Wasserstein regime
            wasser_state, wasser_prob, label_probs = clusterer.get_current_state(close_prices)
            
            # Map states to confidence vector [bull_prob, bear_prob]
            # If HMM indicates BULL, increase bull_prob. If BEAR, increase bear_prob.
            bull_prob = float(hmm_probs.get("BULL", 0.33))
            bear_prob = float(hmm_probs.get("BEAR", 0.33))
            
            # Calculate actual Wasserstein distance to standard return centroid
            returns = np.diff(close_prices) / (close_prices[:-1] + 1e-9)
            std_ret = np.std(returns) if np.std(returns) > 1e-9 else 0.001
            normal_dist = np.random.normal(0, std_ret, len(returns))
            from scipy.stats import wasserstein_distance
            w_dist = float(wasserstein_distance(np.sort(returns), np.sort(normal_dist)))
            
            # Epistemic pass
            epistemic_pass = bool(w_dist < 0.65)
            
            results[symbol] = {
                "timestamp": int(time.time()),
                "source_oracle": "HMM",
                "confidence_vector": [bull_prob, bear_prob],
                "wasserstein_distance": w_dist,
                "epistemic_pass": epistemic_pass,
                "metadata": {
                    "hmm_state": hmm_state,
                    "wasserstein_state": wasser_state,
                    "wasserstein_prob": float(wasser_prob)
                }
            }
        except Exception as e:
            print(f"[HMM_ERR] Error processing {symbol}: {e}")
            
    mt5.shutdown()
    
    # Atomic write to JSON
    temp_file = STATE_FILE + ".tmp"
    with open(temp_file, "w") as f:
        json.dump(results, f, indent=2)
    os.replace(temp_file, STATE_FILE)
    print(f"[HMM] Successfully wrote states for {len(results)} assets.")

if __name__ == "__main__":
    main()
