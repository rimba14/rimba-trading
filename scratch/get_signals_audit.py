import git_arctic
from datetime import datetime

def get_signals_update():
    watchlist = ["EURUSD", "GBPUSD", "XAUUSD", "NAS100", "BTCUSD", "ETHUSD", "SP500", "GER40"]
    try:
        store = git_arctic.get_arctic()
        lib = store['oracle_cache']
        print("\n--- LIVE AI SIGNALS ---")
        for sym in watchlist:
            try:
                h_item = lib.read(f"{sym}_hmm")
                h_data = h_item.data.to_dict('records')[-1]
                
                k_item = lib.read(f"{sym}_kronos")
                k_data = k_item.data.to_dict('records')[-1]
                
                age = int(datetime.now().timestamp() - k_data['timestamp'])
                print(f"[{sym}] Regime: {h_data['state']}, AI_Prob: {k_data['kronos_prob']:.3f}, Age: {age}s")
            except:
                print(f"[{sym}] SIGNAL MISSING OR STALE")
    except Exception as e:
        print(f"ARCTIC_DB_ERR: {e}")

if __name__ == "__main__":
    get_signals_update()
