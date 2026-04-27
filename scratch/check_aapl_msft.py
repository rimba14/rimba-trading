import git_arctic
import time

def check_specifics():
    store = git_arctic.get_arctic()
    lib = store['oracle_cache']
    for sym in ['AAPL', 'MSFT']:
        try:
            k_data = lib.read(f"{sym}_kronos").data.iloc[-1].to_dict()
            h_data = lib.read(f"{sym}_hmm").data.iloc[-1].to_dict()
            xgboost_p = k_data.get('xgboost_prob', 0.5)
            kronos_p = k_data['kronos_prob']
            divergence = abs(kronos_p - xgboost_p)
            age = time.time() - k_data['timestamp']
            
            print(f"[{sym}] Kronos: {kronos_p:.3f}, XGBoost: {xgboost_p:.3f}, Div: {divergence:.3f}")
            print(f"[{sym}] Regime: {h_data['state']}, Age: {int(age)}s")
            
            # Simulated Epistemic Gate
            consensus = (divergence <= 0.30)
            regime_ok = (h_data['state'] != 'RANGE')
            if consensus and regime_ok:
                final_p = kronos_p
                gate = "PASSED"
            else:
                final_p = (kronos_p + xgboost_p) / 2.0
                gate = "FAILED (Reverted to 50/50)"
            
            print(f"[{sym}] Gate: {gate}, Final P: {final_p:.3f}")
            print("-" * 20)
        except Exception as e:
            print(f"[{sym}] Error: {e}")

if __name__ == "__main__":
    check_specifics()
