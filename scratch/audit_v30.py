import time
import os
import sys
sys.path.append(r"C:\Sentinel_Project")
import git_arctic
import pandas as pd
import requests
import json
from dotenv import load_dotenv

load_dotenv(r"C:\Sentinel_Project\.env")

results = {
    "latency": 0.0,
    "stale_assets": [],
    "anomalies": [],
    "tunnel_status": "DISCONNECTED",
    "tickets": []
}

# 1. Cache Freshness & Latency
try:
    start = time.time()
    ac = git_arctic.get_arctic()
    lib = ac['oracle_cache']
    symbols = lib.list_symbols()
    latency = (time.time() - start) * 1000
    results["latency"] = latency

    current_time = time.time()
    
    for sym in symbols:
        if not sym.endswith('_meta'): continue
        df = lib.read(sym).data
        if not df.empty:
            last_row = df.iloc[-1]
            ts = last_row.get('timestamp', 0)
            if current_time - ts > 900:
                results["stale_assets"].append(sym.replace('_meta', ''))
                
            # 2 & 3. Feature Matrix Check
            for feat in ['xgboost_prob', 'kronos_prob', 'wasserstein_state', 'faiss_similarity', 'sentiment_score']:
                val = last_row.get(feat, None)
                if pd.isna(val) or val is None or (isinstance(val, float) and val == 0.0):
                    results["anomalies"].append(f"{sym.replace('_meta', '')}: {feat}={val}")
except Exception as e:
    results["anomalies"].append(f"Cache Error: {str(e)}")

# 4. Sniper Tunnel
try:
    url = os.getenv("SNIPER_HTTP_URL", "http://127.0.0.1:8000")
    r = requests.get(f"{url}/health", timeout=2)
    results["tunnel_status"] = f"ONLINE ({r.status_code})"
except requests.exceptions.RequestException as e:
    try:
        r = requests.get(url, timeout=2)
        results["tunnel_status"] = f"ONLINE ({r.status_code})"
    except Exception as e2:
        results["tunnel_status"] = f"DISCONNECTED"

# 5. SRE Halt Check
try:
    tickets = os.listdir(r"C:\Sentinel_Project\pending_diagnostics")
    results["tickets"] = tickets
except Exception as e:
    pass

print(json.dumps(results, indent=2))
