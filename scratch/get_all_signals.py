import sys
import os
from datetime import datetime

sys.path.append(r"C:\Sentinel_Project")
import sentinel_config
import git_arctic

def main():
    watchlist = sentinel_config.WATCHLIST
    store = git_arctic.get_arctic()
    lib = store['oracle_cache']
    
    results = []
    
    print("=== WATCHLIST SCAN ===")
    for sym in watchlist:
        try:
            h_item = lib.read(f"{sym}_hmm")
            h_data = h_item.data.to_dict('records')[-1]
            
            k_item = lib.read(f"{sym}_kronos")
            k_data = k_item.data.to_dict('records')[-1]
            
            # Since some might not have XGBoost, let's try reading it safely
            x_prob = 0.5
            try:
                x_item = lib.read(f"{sym}_xgb")
                x_data = x_item.data.to_dict('records')[-1]
                x_prob = x_data.get('xgb_prob', 0.5)
            except:
                pass

            p_val = k_data.get('kronos_prob', 0.5)
            hmm_state = h_data.get('state', 'UNKNOWN')
            hmm_prob = h_data.get('prob', 0.0)
            
            age = int(datetime.now().timestamp() - k_data['timestamp'])
            
            # Calculate conviction
            # P_blend is usually the mean of Kronos and XGBoost if both exist
            p_blend = (p_val + x_prob) / 2.0
            
            # Determine direction
            direction = "NEUTRAL"
            norm_p = 0.5
            if p_blend >= 0.60:
                direction = "BUY"
                norm_p = p_blend
            elif p_blend <= 0.40:
                direction = "SELL"
                norm_p = 1.0 - p_blend

            results.append({
                "symbol": sym,
                "direction": direction,
                "hmm_state": hmm_state,
                "hmm_prob": hmm_prob,
                "kronos": p_val,
                "xgb": x_prob,
                "p_blend": p_blend,
                "norm_p": norm_p,
                "age": age
            })
        except Exception as e:
            # print(f"[{sym}] Skip: {e}")
            pass

    # Sort results by norm_p descending (excluding NEUTRAL)
    filtered = [r for r in results if r["direction"] != "NEUTRAL" and r["age"] < 7200]
    filtered.sort(key=lambda x: x["norm_p"], reverse=True)
    
    print(f"\nFound {len(filtered)} active signals (< 2 hours old):")
    for r in filtered:
        print(f"[{r['symbol']}] {r['direction']} | Norm P: {r['norm_p']:.4f} | HMM: {r['hmm_state']} ({r['hmm_prob']:.1%}) | Kronos: {r['kronos']:.3f} | XGB: {r['xgb']:.3f} | Age: {r['age']}s")

if __name__ == "__main__":
    main()
