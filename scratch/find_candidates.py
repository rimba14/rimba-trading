import git_arctic
import time
from sentinel_config import WATCHLIST

def find_best_candidates():
    store = git_arctic.get_arctic()
    lib = store['oracle_cache']
    candidates = []
    
    for sym in WATCHLIST:
        try:
            k_data = lib.read(f"{sym}_kronos").data.iloc[-1].to_dict()
            h_data = lib.read(f"{sym}_hmm").data.iloc[-1].to_dict()
            p = k_data['kronos_prob']
            dist = abs(p - 0.5)
            candidates.append((sym, p, h_data['state'], dist))
        except:
            continue
            
    candidates.sort(key=lambda x: x[3], reverse=True)
    
    print("--- TOP 10 CANDIDATES BY AI CONVICTION ---")
    for sym, p, regime, dist in candidates[:10]:
        print(f"[{sym}] Prob: {p:.3f}, Regime: {regime}")

if __name__ == "__main__":
    find_best_candidates()
