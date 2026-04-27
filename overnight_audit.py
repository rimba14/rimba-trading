import MetaTrader5 as mt5
import json
import os
from datetime import datetime, timezone

def audit():
    if not mt5.initialize():
        print("[FAIL] MT5 Initialization Failed")
        return

    positions = mt5.positions_get()
    if not positions:
        print("[INFO] No open positions found.")
        return

    print(f"[INFO] Auditing {len(positions)} positions...")
    
    thesis_path = "C:\\Sentinel_Project\\position_thesis.json"
    if not os.path.exists(thesis_path):
        print("[FAIL] position_thesis.json missing!")
        return

    with open(thesis_path, 'r') as f:
        thesis = json.load(f)

    all_secure = True
    for p in positions:
        t = thesis.get(str(p.ticket), {})
        s_sl = t.get("sl")
        s_tp = t.get("tp")
        
        # Validation: Broker SL/TP should be 0.0 for Stealth
        # Validation: Software SL/TP should be non-zero
        broker_clean = (p.sl == 0.0 and p.tp == 0.0)
        software_active = (s_sl is not None and s_tp is not None and s_sl > 0)
        
        status = "OK" if (broker_clean and software_active) else "FAULT"
        if status == "FAULT": all_secure = False
        
        print(f"Ticket: {p.ticket} | Sym: {p.symbol} | Broker SL/TP: {p.sl}/{p.tp} | Stealth SL/TP: {s_sl}/{s_tp} | [{status}]")

    print("-" * 50)
    # Heartbeat Check
    log_path = "C:\\Sentinel_Project\\vantage_production.log"
    hb_ok = False
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            lines = f.readlines()
            heartbeats = [l for l in lines if "[HEARTBEAT]" in l]
            if heartbeats:
                latest = heartbeats[-1]
                ts_str = latest.split("] ")[1].split(" |")[0]
                log_dt = datetime.fromisoformat(ts_str.replace(" ", "T")).replace(tzinfo=timezone.utc)
                diff = (datetime.now(timezone.utc) - log_dt).total_seconds()
                if diff < 300: # 5 mins
                    hb_ok = True
                    print(f"[PASS] Loop Heartbeat: ACTIVE ({int(diff)}s ago)")
                else:
                    print(f"[FAIL] Loop Heartbeat: STALE ({int(diff)}s ago)")
            else:
                print("[FAIL] No Heartbeats found in log.")
    else:
        print("[FAIL] Production log missing.")

    if all_secure and hb_ok:
        print("\n[RESULT] SYSTEM SECURE. ALL POSITIONS SHIELDED. SLEEP PROTOCOL GREEN.")
    else:
        print("\n[RESULT] SYSTEM VULNERABLE. MANUAL INTERVENTION RECOMMENDED.")
    
    mt5.shutdown()

if __name__ == "__main__":
    audit()
