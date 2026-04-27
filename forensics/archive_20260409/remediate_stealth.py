import MetaTrader5 as mt5
import json
import os
import time

def remediate():
    if not mt5.initialize():
        print("[FAIL] MT5 Initialization Failed")
        return

    positions = mt5.positions_get()
    if not positions:
        print("[INFO] No open positions found.")
        return

    thesis_path = "C:\\Sentinel_Project\\position_thesis.json"
    thesis = {}
    if os.path.exists(thesis_path):
        with open(thesis_path, 'r') as f:
            thesis = json.load(f)

    print(f"[ACTION] Synchronizing {len(positions)} positions to Stealth mode...")
    
    for p in positions:
        ticket_str = str(p.ticket)
        # 1. Capture current targets if thesis is empty for this ticket
        if ticket_str not in thesis or thesis[ticket_str].get("sl") is None:
            # If broker targets are 0.0, we have a PROBLEM (no targets found). 
            # We'll use a standard 2% offset if missing.
            sl_val = p.sl if p.sl != 0.0 else (p.price_open * 0.98 if p.type == 0 else p.price_open * 1.02)
            tp_val = p.tp if p.tp != 0.0 else (p.price_open * 1.05 if p.type == 0 else p.price_open * 0.95)
            
            thesis[ticket_str] = {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "sl": sl_val,
                "tp": tp_val,
                "entry": p.price_open,
                "reason": "Institutional Migration (Phase 67)"
            }
            print(f"[SYNC] Ticket {p.ticket} targets captured in software.")

        # 2. CLEAR BROKER-SIDE SL/TP (Transition to Stealth)
        if p.sl != 0.0 or p.tp != 0.0:
            from gitagent_action_layer import get_action_layer
            al = get_action_layer()
            result = al.modify_position_sltp(p.symbol, p.ticket, 0.0, 0.0)
            if result and result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"[FAIL] Could not clear broker SL/TP for {p.ticket}: {result.comment}")
            else:
                print(f"[STEALTH] Ticket {p.ticket} is now shielded (Broker targets removed).")


    # 3. Save finalized thesis
    with open(thesis_path, 'w') as f:
        json.dump(thesis, f, indent=4)
    print(f"[SUCCESS] {thesis_path} updated. All positions are now in Stealth mode.")
    
    mt5.shutdown()

if __name__ == "__main__":
    remediate()
