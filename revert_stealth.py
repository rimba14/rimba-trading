import MetaTrader5 as mt5
import json
import os
import pandas as pd

def revert():
    if not mt5.initialize():
        print("[FAIL] MT5 Initialization Failed")
        return

    positions = mt5.positions_get()
    if not positions:
        print("[INFO] No open positions found.")
        return

    thesis_path = "C:\\Sentinel_Project\\position_thesis.json"
    if not os.path.exists(thesis_path):
        print(f"[FAIL] Thesis file {thesis_path} missing.")
        return

    with open(thesis_path, 'r') as f:
        thesis = json.load(f)

    print(f"[ACTION] Reverting {len(positions)} positions from Stealth to Broker-Server...")
    
    results = []
    for p in positions:
        ticket_str = str(p.ticket)
        t_data = thesis.get(ticket_str, {})
        
        sl = t_data.get("sl")
        tp = t_data.get("tp")
        
        # Fallback if thesis is missing data for a live ticket
        if not sl or not tp:
            print(f"[WARN] Ticket {p.ticket} ({p.symbol}) has no targets in thesis. Skipping.")
            results.append({"ticket": p.ticket, "symbol": p.symbol, "status": "SKIPPED (No Thesis Data)"})
            continue

        # Execute Broker Update
        from gitagent_action_layer import get_action_layer
        res = get_action_layer().modify_position_sltp(p.symbol, p.ticket, sl, tp)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:

            print(f"[SUCCESS] Ticket {p.ticket} ({p.symbol}) targets restored to Broker.")
            results.append({"ticket": p.ticket, "symbol": p.symbol, "status": "SUCCESS", "sl": sl, "tp": tp})
            # OPTIONAL: Keep them in thesis but mark as synced? 
        else:
            print(f"[FAIL] Ticket {p.ticket} ({p.symbol}) Error: {res.comment}")
            results.append({"ticket": p.ticket, "symbol": p.symbol, "status": f"FAILED: {res.comment}"})

    # Summary Report
    df = pd.DataFrame(results)
    print("\n--- REVERSION SUMMARY ---")
    print(df.to_string(index=False))
    
    mt5.shutdown()

if __name__ == "__main__":
    revert()
