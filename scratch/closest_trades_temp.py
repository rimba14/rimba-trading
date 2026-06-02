import sys
sys.path.append(r'C:\Sentinel_Project')
import git_arctic
from sentinel_config import WATCHLIST

ac = git_arctic.get_arctic()
if 'oracle_cache' not in ac.list_libraries():
    print("oracle_cache not found.")
    sys.exit()

lib = ac['oracle_cache']

results = []
for sym in WATCHLIST:
    try:
        item = lib.read(f"{sym}_kronos")
        data = item.data.iloc[-1]
        p = float(data['kronos_prob'])
        strength = abs(p - 0.5)
        direction = 'BUY' if p > 0.5 else 'SELL'
        
        # Read Hmm
        hmm_state = "UNKNOWN"
        try:
            h_item = lib.read(f"{sym}_hmm")
            h_data = h_item.data.iloc[-1]
            hmm_state = str(h_data['state'])
        except:
            pass

        results.append({
            'sym': sym, 
            'p': p, 
            'dir': direction, 
            'strength': strength,
            'hmm': hmm_state
        })
    except Exception as e:
        continue

results.sort(key=lambda x: x['strength'], reverse=True)
print("\n--- TOP 10 CLOSEST TRADES TO FIRING (Highest Conviction) ---")
print(f"{'Symbol':<10} | {'Dir':<4} | {'Prob':<6} | {'Strength':<8} | {'HMM Regime':<10}")
print("-" * 55)
for r in results[:10]:
    print(f"{r['sym']:<10} | {r['dir']:<4} | {r['p']:.4f} | {r['strength']:.4f}   | {r['hmm']:<10}")
