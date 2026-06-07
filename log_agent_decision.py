import json
import os
import time
import uuid
from datetime import datetime

TRAILS_DIR = os.path.join(os.path.dirname(__file__), "data", "decision_trails")

def log_decision(agent: str, symbol: str, target_direction: str, calculated_conviction: float):
    os.makedirs(TRAILS_DIR, exist_ok=True)
    
    timestamp = time.time()
    iso_time = datetime.utcfromtimestamp(timestamp).isoformat() + "Z"
    
    # Ingest from runtime_context.json if available
    context_path = os.path.join(os.path.dirname(__file__), "config", "runtime_context.json")
    runtime_context_data = {}
    if os.path.exists(context_path):
        try:
            with open(context_path, "r") as f:
                runtime_context_data = json.load(f)
        except:
            pass

    payload = {
        "id": str(uuid.uuid4()),
        "agent": agent,
        "symbol": symbol,
        "target_direction": target_direction,
        "calculated_conviction": calculated_conviction,
        "timestamp_map": {
            "unix": timestamp,
            "iso": iso_time
        },
        "runtime_context": {
            "active_regime": runtime_context_data.get("regime", "UNKNOWN"),
            "volatility_multiplier": runtime_context_data.get("volatility_multiplier", 1.0),
            "cross_asset_correlation_flag": runtime_context_data.get("cross_asset_correlation_flag", False)
        },
        "guardrail_states": {
            "epistemic_gate_cleared": True if calculated_conviction > 0.82 else False,
            "entropy_blocker_active": False,
            "macro_veto": False
        },
        "final_pnl_outcome": None,
        "processed_by_hermes": False
    }
    
    filename = f"{agent}_{symbol}_{int(timestamp)}.json"
    filepath = os.path.join(TRAILS_DIR, filename)
    
    try:
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=4)
    except Exception as e:
        print(f"[HARNESS] Failed to write decision log: {e}")
        
    return filepath
