import qlib
from qlib.data import D
import pandas as pd
import numpy as np
import json
import os

def initialize_offline_factory():
    qlib.init(provider_uri="/app/data/qlib_bin", region="us")

def evaluate_formulaic_candidate(formula_string, start_dt="2024-01-01", end_dt="2026-05-01"):
    try:
        instruments = D.instruments('all')
        feature_series = D.features(instruments, [formula_string], start_time=start_dt, end_time=end_dt)
        forward_returns = D.features(instruments, ['Ref($close, -1)/$close - 1'], start_time=start_dt, end_time=end_dt)
        
        # Calculate cross-sectional Information Coefficient (IC)
        valid_mask = feature_series.notna().iloc[:, 0] & forward_returns.notna().iloc[:, 0]
        if valid_mask.sum() < 500:
            return 0.0
        ic = feature_series[valid_mask].corrwith(forward_returns[valid_mask].iloc[:, 0]).mean()
        return float(ic) if not np.isnan(ic) else 0.0
    except Exception:
        return 0.0

def run_alpha_generation_epoch():
    initialize_offline_factory()
    
    primitives = ["$close", "$open", "$volume", "$high", "$low"]
    operators = ["Ref({}, 5)", "Mean({}, 10)", "Std({}, 20)", "Delta({}, 1)"]
    discovered_registry = {}
    
    for prim in primitives:
        for op in operators:
            candidate_formula = op.format(prim)
            ic_score = evaluate_formulaic_candidate(candidate_formula)
            
            # Filter threshold for meaningful predictive signal
            if abs(ic_score) >= 0.045:
                alpha_id = f"QLIB_ALPHA_{len(discovered_registry) + 1:03d}"
                discovered_registry[alpha_id] = {
                    "formula": candidate_formula,
                    "ic": ic_score,
                    "weight": float(np.tanh(ic_score * 10))
                }
                
    # Enforce atomic write protocol
    target_path = "/app/registry/alphas_optimized.json"
    tmp_path = f"{target_path}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(discovered_registry, f, indent=4)
    os.rename(tmp_path, target_path)

if __name__ == "__main__":
    run_alpha_generation_epoch()
