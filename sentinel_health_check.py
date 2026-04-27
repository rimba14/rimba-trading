import MetaTrader5 as mt5
import pandas as pd
import os
import time
from datetime import datetime, timezone
import subprocess
import requests

def run_check(name, description, check_fn):
    print(f"[*] Checking {name} ({description})...", end=" ", flush=True)
    try:
        success, details = check_fn()
        if success:
            print(" [PASS]")
            return {"status": "PASS", "details": details}
        else:
            print(f" [FAIL] !! {details}")
            return {"status": "FAIL", "details": details}
    except Exception as e:
        print(f" [ERROR] {e}")
        return {"status": "ERROR", "details": str(e)}

# --- Layer 1: Connectivity ---
def check_mt5():
    if not mt5.initialize():
        return False, "Failed to initialize MT5"
    terminal_info = mt5.terminal_info()
    if not terminal_info.connected:
        return False, "MT5 initialized but not connected to broker"
    return True, f"Broker: {terminal_info.company} | Account: {mt5.account_info().login}"

def check_vix():
    try:
        url = "https://query1.finance.yahoo.com/v7/finance/chart/^VIX?interval=1m&range=1d"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            val = res.json()['chart']['result'][0]['meta']['regularMarketPrice']
            return True, f"Current VIX: {val:.2f}"
    except Exception as e:
        return False, str(e)

# --- Layer 2: Infrastructure ---
def check_junctions():
    p = os.path.expandvars(r"%LOCALAPPDATA%\Programs\cursor")
    if not os.path.exists(p): return False, "Cursor junction path missing"
    # Use fsutil for ultimate accuracy on Windows junctions
    res = subprocess.run(["fsutil", "reparsepoint", "query", p], capture_output=True, text=True)
    if "Substitute Name:" in res.stdout and "C:\\Sentinel_Project\\\Programs\\cursor" in res.stdout:
        return True, "Cursor junction confirmed: C: -> E:"
    return False, "Cursor folder exists but is not a verified reparse point"

def check_grafana():
    try:
        res = requests.get("http://localhost:3000/api/health", timeout=5)
        if res.status_code == 200:
            return True, f"Grafana Local Healthy (v{res.json().get('version')})"
    except:
        pass
    return False, "Grafana service unreachable on port 3000"

# --- Layer 3: Conductor ---
def check_heartbeat():
    log_path = "C:\\Sentinel_Project\\vantage_production.log"
    if not os.path.exists(log_path): return False, "Production log missing"
    with open(log_path, 'r') as f:
        lines = f.readlines()
        if not lines: return False, "Log is empty"
        last_line = lines[-1]
        # Look for [HEARTBEAT] timestamp
        # Logic: find latest heartbeat
        heartbeats = [l for l in lines if "[HEARTBEAT]" in l]
        if not heartbeats: return False, "No [HEARTBEAT] entries found in log"
        latest = heartbeats[-1]
        # Extract timestamp: [HEARTBEAT] 2026-04-06 23:48:13...
        ts_str = latest.split("] ")[1].split(" |")[0]
        log_dt = datetime.fromisoformat(ts_str.replace(" ", "T"))
        diff = (datetime.now(timezone.utc) - log_dt.replace(tzinfo=timezone.utc)).total_seconds()
        if diff < 600: # 10 mins
            return True, f"Heartbeat active ({int(diff)}s ago)"
        return False, f"Heartbeat STALE ({int(diff)}s ago)"

def check_risk():
    acc = mt5.account_info()
    if not acc: return False, "Could not fetch account info"
    margin_lvl = acc.margin_level
    pos_count = len(mt5.positions_get())
    status = "PASS" if margin_lvl > 200 else "WARNING"
    return (status == "PASS"), f"Margin Level: {margin_lvl:.1f}% | Positions: {pos_count}/15"

if __name__ == "__main__":
    print("="*60)
    print(f"SENTINEL HUB HEALTH AUDIT | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    results = {}
    results['MT5'] = run_check("MT5 Bridge", "Broker Connectivity", check_mt5)
    results['VIX'] = run_check("VIX Sensor", "Market Volatility Feed", check_vix)
    results['Junc'] = run_check("E-Drive Junctions", "Storage & Redirection", check_junctions)
    results['Grafana'] = run_check("Grafana Local", "Visualization Engine", check_grafana)
    results['Heartbeat'] = run_check("Conductor Loop", "Heartbeat Vitality", check_heartbeat)
    results['Risk'] = run_check("Account Hygiene", "Margin & Exposure", check_risk)
    
    print("="*60)
    total_fails = sum(1 for v in results.values() if v['status'] != "PASS")
    if total_fails == 0:
        print("RESULT: SYSTEM GREEN. ALL SYSTEMS INSTITUTIONAL GRADE.")
    else:
        print(f"RESULT: SYSTEM AMBER/RED. {total_fails} COMPONENT(S) REQUIRE ATTENTION.")
    print("="*60)
    mt5.shutdown()
