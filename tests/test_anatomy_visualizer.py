import os
import json
import numpy as np
import pytest
from gitagent_anatomy_visualizer import (
    load_anatomy_data,
    extract_trajectory_features,
    plot_anatomy
)

def test_load_anatomy_data(tmp_path):
    d = tmp_path / "test.json"
    data = {"test": "data"}
    d.write_text(json.dumps(data))

    loaded = load_anatomy_data(str(d))
    assert loaded == data

def test_load_anatomy_data_nonexistent():
    assert load_anatomy_data("nonexistent.json") is None

def test_extract_trajectory_features():
    traj = [
        {
            "step_bar_idx": 1,
            "price": 1.1,
            "sl": 1.0,
            "tp": 1.2,
            "conviction": 0.5,
            "hmm_state": "BULL",
            "feature_shap_importance": {"feat1": 0.1}
        },
        {
            "step_bar_idx": 2,
            "price": 1.15,
            "sl": 1.0,
            "tp": 1.2,
            "conviction": 0.6,
            "hmm_state": "BULL",
            "feature_shap_importance": {"feat1": 0.2, "feat2": -0.1}
        }
    ]

    features = extract_trajectory_features(traj)

    assert features["steps"] == [1, 2]
    assert features["prices"] == [1.1, 1.15]
    assert features["sls"] == [1.0, 1.0]
    assert features["tps"] == [1.2, 1.2]
    assert features["convictions"] == [0.5, 0.6]
    assert features["hmm_states"] == ["BULL", "BULL"]
    assert features["shap_keys"] == ["feat1", "feat2"]
    assert features["shap_matrix"].shape == (2, 2)
    assert np.allclose(features["shap_matrix"], [[0.1, 0.2], [0.0, -0.1]])

def test_plot_anatomy_integration(tmp_path):
    json_path = tmp_path / "trade_anatomy_123.json"
    data = {
        "trajectory": [
            {
                "step_bar_idx": 1,
                "price": 1.1,
                "sl": 1.0,
                "tp": 1.2,
                "conviction": 0.5,
                "hmm_state": "BULL",
                "feature_shap_importance": {"feat1": 0.1}
            }
        ]
    }
    json_path.write_text(json.dumps(data))

    plot_anatomy(str(json_path))

    output_path = tmp_path / "trade_anatomy_123.png"
    assert output_path.exists()
