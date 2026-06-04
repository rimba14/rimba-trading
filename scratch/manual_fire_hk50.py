import time
import requests
import logging

logging.basicConfig(level=logging.INFO)

def fire_hk50():
    try:
        from arcticdb import Arctic
        store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
        row = store["oracle_cache"].read("HK50_meta").data.iloc[-1]
    except Exception as e:
        logging.error(f"Failed to read cache: {e}")
        return

    payload = {
        "symbol": "HK50",
        "direction": "BUY",
        "strategy_type": "MEAN_REVERSION",
        "conviction": float(row.get("meta_conviction", 0.8627)),
        "xgb_p": float(row.get("xgb_p", 0.5)),
        "ddqn_p": float(row.get("ddqn_p", 0.5)),
        "wasserstein_state": str(row.get("hmm_state", "CRISIS TAIL")),
        "vrs": 1.0,
        "rsi": float(row.get("rsi", 30.0)),
        "vpin": float(row.get("vpin", 0.5)),
        "size_multiplier": 1.0,
        "sl": 0.0,
        "tp": 0.0,
        "tag": "MANUAL_FIRE_HK50"
    }

    try:
        logging.info("Firing HK50 manually via Direct HTTP Bridge...")
        response = requests.post("http://127.0.0.1:8000/execute_trade", json=payload, timeout=5)
        if response.status_code == 200:
            logging.info(f"[OK] Trade Executed: {response.json()}")
        else:
            logging.error(f"[FAIL] Execution blocked by Sniper. Status: {response.status_code}, Detail: {response.text}")
    except Exception as e:
        logging.error(f"HTTP Post failed: {e}")

if __name__ == "__main__":
    fire_hk50()
