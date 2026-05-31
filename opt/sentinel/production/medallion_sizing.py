import numpy as np

def compute_cades_dynamic_allocation(base_signal_direction, conviction_package, trust_gate_failed):
    """
    Integrates the updated conformal interval metrics and trust gates directly into 
    the active live position sizing logic layers.
    """
    # 1. Hard Structural Veto Rule Execution
    if trust_gate_failed or conviction_package["neutral_ground_override"] == True:
        print("[RISK_VETO]: Forcing absolute liquidation / position protection mode (Sizing: 0.0000)")
        return 0.0000
        
    p_mid = conviction_package["calibrated_midpoint"]
    width = conviction_package["uncertainty_width"]
    
    # Enforce strict Epistemic Gate Threshold
    if p_mid < 0.82:
        print(f"[EPISTEMIC_GATE_HOLD]: Conviction score {p_mid:.4f} below barrier. Denying order execution.")
        return 0.0000
        
    # 2. Classic Fractional Quarter-Kelly Baseline Generation
    b_ratio = 1.0 # 1:1 Risk-to-Reward Ratio assumption profile
    q_fractional_kelly = (p_mid * (b_ratio + 1) - 1) / b_ratio
    base_allocation = q_fractional_kelly * 0.25
    
    # 3. Dynamic Conformal Uncertainty Penalty Modulation
    # Scale allocation downward as the width of our uncertainty interval expands
    uncertainty_scaling_factor = 1.5
    penalty_multiplier = np.clip(1.0 - (width * uncertainty_scaling_factor), 0.0, 1.0)
    
    final_allocated_size = base_allocation * penalty_multiplier
    final_allocated_size = np.clip(final_allocated_size, 0.0, 1.0) # Absolute hard asset safety ceiling bounding
    
    print(f"[ALLOCATION_CALCULATED] Midpoint: {p_mid:.4f} | Width: {width:.4f} | Size: {final_allocated_size:.4f}")
    return float(final_allocated_size)
