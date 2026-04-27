import json
import os
from datetime import datetime, timezone, timedelta

def create_dummy_audit():
    log_path = r"C:\Sentinel_Project\cognition_bridge.json"
    dummy_data = [
        {
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=4)).strftime('%Y-%m-%d %H:%M:%S UTC'),
            "symbol": "BTCUSD",
            "hmm_state": "BULL",
            "kronos_prob": 0.582,
            "xgboost_prob": 0.610,
            "final_p": 0.596,
            "f_star": 0.024,
            "legend_active": False,
            "reasoning": "Oracle Prime"
        },
        {
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S UTC'),
            "symbol": "XAUUSD",
            "hmm_state": "BEAR",
            "kronos_prob": 0.410,
            "xgboost_prob": 0.385,
            "final_p": 0.397,
            "f_star": 0.031,
            "legend_active": False,
            "reasoning": "Oracle Prime"
        },
        {
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S UTC'),
            "symbol": "NAS100",
            "hmm_state": "BULL",
            "kronos_prob": 0.520,
            "xgboost_prob": 0.510,
            "final_p": 0.850,
            "f_star": 0.080,
            "legend_active": True,
            "reasoning": "Legend Override"
        },
        {
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S UTC'),
            "symbol": "EURUSD",
            "hmm_state": "BULL",
            "kronos_prob": 0.655,
            "xgboost_prob": 0.680,
            "final_p": 0.667,
            "f_star": 0.045,
            "legend_active": False,
            "reasoning": "Oracle Prime"
        },
        {
            "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            "symbol": "ETHUSD",
            "hmm_state": "BEAR",
            "kronos_prob": 0.440,
            "xgboost_prob": 0.420,
            "final_p": 0.430,
            "f_star": 0.021,
            "legend_active": False,
            "reasoning": "Oracle Prime"
        }
    ]

    with open(log_path, 'w') as f:
        json.dump(dummy_data, f, indent=4)
    
    print(f"[SUCCESS] {log_path} created with 5 simulated cognition events.")

if __name__ == "__main__":
    create_dummy_audit()
