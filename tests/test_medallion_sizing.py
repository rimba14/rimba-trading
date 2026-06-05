import pytest
from opt.sentinel.production.medallion_sizing import compute_cades_dynamic_allocation

def test_trust_gate_veto():
    conviction_package = {
        "neutral_ground_override": False,
        "calibrated_midpoint": 0.9,
        "uncertainty_width": 0.1
    }
    result = compute_cades_dynamic_allocation(1, conviction_package, True)
    assert result == 0.0

def test_neutral_ground_override():
    conviction_package = {
        "neutral_ground_override": True,
        "calibrated_midpoint": 0.9,
        "uncertainty_width": 0.1
    }
    result = compute_cades_dynamic_allocation(1, conviction_package, False)
    assert result == 0.0

def test_final_allocation_clipping():
    conviction_package = {
        "neutral_ground_override": False,
        "calibrated_midpoint": 10.0, # Extremely high to force base_allocation > 1.0
        "uncertainty_width": 0.0
    }
    # Kelly: (10.0 * 2 - 1) / 1 = 19.0
    # Base Allocation: 19.0 * 0.25 = 4.75
    # Penalty Multiplier: 1.0 - (0.0 * 1.5) = 1.0
    # Final Allocation before clipping: 4.75
    # Clipped: 1.0
    result = compute_cades_dynamic_allocation(1, conviction_package, False)
    assert result == 1.0

def test_uncertainty_penalty_clipping():
    conviction_package = {
        "neutral_ground_override": False,
        "calibrated_midpoint": 0.9,
        "uncertainty_width": 0.7
    }
    # Penalty Multiplier: np.clip(1.0 - (0.7 * 1.5), 0.0, 1.0) = np.clip(-0.05, 0.0, 1.0) = 0.0
    result = compute_cades_dynamic_allocation(1, conviction_package, False)
    assert result == 0.0

def test_successful_allocation_calculation():
    conviction_package = {
        "neutral_ground_override": False,
        "calibrated_midpoint": 0.9,
        "uncertainty_width": 0.1
    }
    # Kelly: (0.9 * (1 + 1) - 1) / 1 = 0.8
    # Base Allocation: 0.8 * 0.25 = 0.2
    # Penalty Multiplier: 1.0 - (0.1 * 1.5) = 0.85
    # Final Allocation: 0.2 * 0.85 = 0.17
    result = compute_cades_dynamic_allocation(1, conviction_package, False)
    assert pytest.approx(result) == 0.17

def test_epistemic_gate_threshold():
    conviction_package = {
        "neutral_ground_override": False,
        "calibrated_midpoint": 0.81,
        "uncertainty_width": 0.1
    }
    result = compute_cades_dynamic_allocation(1, conviction_package, False)
    assert result == 0.0
