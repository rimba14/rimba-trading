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
    
    for sym in watchlist:
        try:
            m_item = lib.read(f"{sym}_meta")
            m_data = m_item.data.to_dict('records')[-1]
            
            age = int(datetime.now().timestamp() - m_data['timestamp'])
            if age > 43200: # up to 12 hours
                continue
                
            p_dir = m_data['primary_dir']
            if p_dir == 0:
                continue # Neutral
                
            direction = "BUY" if p_dir == 1 else "SELL"
            
            results.append({
                "symbol": sym,
                "dir": direction,
                "conviction": m_data['meta_conviction'],
                "hmm_state": m_data['hmm_state'],
                "strategy": m_data['strategy_type'],
                "age": age
            })
        except:
            pass
            
    # Sort by conviction (dist from 0.5) descending
    results.sort(key=lambda x: abs(x["conviction"] - 0.5), reverse=True)
    
    print("=== LIVE META SIGNALS (UP TO 12 HOURS OLD) ===")
    for r in results:
        # Check alignment
        aligned = False
        if r["dir"] == "BUY" and r["hmm_state"] in ["BULL", "RANGE"]:
            aligned = True
        elif r["dir"] == "SELL" and r["hmm_state"] in ["BEAR", "RANGE"]:
            aligned = True
            
        align_str = "ALIGNED" if aligned else "MISALIGNED"
        print(f"[{r['symbol']}] {r['dir']} | Conviction: {r['conviction']:.4f} | HMM: {r['hmm_state']} ({align_str}) | Strategy: {r['strategy']} | Age: {r['age']}s")

if __name__ == "__main__":
    main()
