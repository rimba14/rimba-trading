import os
import sys
import time
import json
import numpy as np

# Add paths to make sure we can import other gitagent modules if needed
sys.path.append(r"C:\Users\ADMIN\.antigravity\rimba-trading")
sys.path.append(r"C:\Sentinel_Project")

import gitagent_mixts as mixts
import sentinel_config as cfg

# Define output path
STATE_DIR = r"C:\Sentinel_Project\data"
if not os.path.exists(STATE_DIR):
    STATE_DIR = r"C:\Users\ADMIN\.antigravity\rimba-trading\data"
os.makedirs(STATE_DIR, exist_ok=True)
STATE_FILE = os.path.join(STATE_DIR, "mixts_state.json")

def main():
    watchlist = cfg.WATCHLIST
    results = {}
    
    # Initialize the MixTS Agent
    agent = mixts.MixTSAgent()
    
    for symbol in watchlist:
        try:
            # Sample regime index, theta weights, and priors
            s, theta, priors = agent.sample_regime_and_weights()
            
            # Map priors to a 2-dimensional confidence vector
            # E.g., probability of bullish/trend regimes (0 and 2) vs range/bear regimes (1 and 3)
            bull_prob = float(priors[0] + priors[2]) if len(priors) >= 3 else float(priors[0])
            bear_prob = 1.0 - bull_prob
            
            # Use anomaly mean as a proxy for wasserstein distance / distribution change
            w_dist = float(agent.anomaly_mean)
            
            # Epistemic pass checks if anomaly mean is within bounds
            epistemic_pass = bool(w_dist < 0.65)
            
            results[symbol] = {
                "timestamp": int(time.time()),
                "source_oracle": "MIXTS",
                "confidence_vector": [bull_prob, bear_prob],
                "wasserstein_distance": w_dist,
                "epistemic_pass": epistemic_pass,
                "metadata": {
                    "sampled_regime": s,
                    "theta": theta,
                    "priors": priors
                }
            }
        except Exception as e:
            print(f"[MIXTS_ERR] Error processing {symbol}: {e}")
            
    # Atomic write to JSON
    temp_file = STATE_FILE + ".tmp"
    with open(temp_file, "w") as f:
        json.dump(results, f, indent=2)
    os.replace(temp_file, STATE_FILE)
    print(f"[MIXTS] Successfully wrote states for {len(results)} assets.")

if __name__ == "__main__":
    main()
