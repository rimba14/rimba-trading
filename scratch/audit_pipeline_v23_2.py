import MetaTrader5 as mt5
import requests
import json
import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

def audit_pipeline():
    report = []
    report.append("=== PIPELINE INTEGRITY AUDIT (v23.2) ===")
    
    # 1. Execution Loop: MT5 Connection
    if not mt5.initialize():
        report.append("[EXECUTION] MT5 Init: FAILED")
    else:
        info = mt5.terminal_info()
        if info:
            report.append(f"[EXECUTION] MT5 Terminal: ALIVE (Connected: {info.connected})")
            # report.append(f"[EXECUTION] Terminal Info: {info._asdict()}")
        else:
            report.append("[EXECUTION] MT5 Terminal: FAILED to return info")
        
        # 2. Data Loop: copy_ticks_range
        symbol = "XAUUSD"
        to_date = datetime.now()
        from_date = to_date - timedelta(minutes=5)
        ticks = mt5.copy_ticks_range(symbol, from_date, to_date, mt5.COPY_TICKS_ALL)
        if ticks is not None and len(ticks) > 0:
            report.append(f"[DATA] Tick Stream: ACTIVE ({len(ticks)} ticks pulled for {symbol})")
            # Check for NaN
            df = pd.DataFrame(ticks)
            if df.isnull().values.any():
                report.append("[DATA] NaN Detection: WARNING (NaN propagation detected)")
            else:
                report.append("[DATA] NaN Detection: CLEAN")
        else:
            report.append(f"[DATA] Tick Stream: FAILED (No ticks for {symbol})")

    # 3. Risk Loop: Port 8001
    try:
        resp = requests.get("http://localhost:8001/status", timeout=2)
        if resp.status_code == 200:
            status_data = resp.json()
            report.append(f"[RISK] Risk Agent (8001): ONLINE (Version: {status_data.get('version')})")
            if "v23.2" in status_data.get('version', ''):
                report.append("[RISK] Dissonance Veto: ACTIVE")
            else:
                report.append("[RISK] Dissonance Veto: INACTIVE (Old Version)")
        else:
            report.append(f"[RISK] Risk Agent (8001): ERROR (Status {resp.status_code})")
    except Exception as e:
        report.append(f"[RISK] Risk Agent (8001): UNREACHABLE ({e})")

    # 4. Logic Loop: Hysteresis & FAISS (Static Analysis)
    # Checking mixts_router.py for v23.2 logic
    try:
        with open("C:/Sentinel_Project/mixts_router.py", "r") as f:
            content = f.read()
            if "faiss_sim < -0.30" in content and "max(0.85" in content:
                report.append("[LOGIC] FAISS Dynamic Scaling: CONFIGURED")
            else:
                report.append("[LOGIC] FAISS Dynamic Scaling: MISSING or INCORRECT")
            
            if "0.60" in content or "0.40" in content or "0.65" in content: # Checking for bounds
                report.append("[LOGIC] Hysteresis Bounds: DETECTED")
    except Exception as e:
        report.append(f"[LOGIC] Static Audit: FAILED ({e})")

    mt5.shutdown()
    return "\n".join(report)

if __name__ == "__main__":
    print(audit_pipeline())
