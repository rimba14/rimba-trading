import os
import json
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import sys

# Mock dependencies before importing the module
mock_vbt = MagicMock()
sys.modules['vectorbt'] = mock_vbt
mock_mt5 = MagicMock()
sys.modules['MetaTrader5'] = mock_mt5
sys.modules['gitagent_utils'] = MagicMock()
mock_sentinel_config = MagicMock()
mock_sentinel_config.BROKER_SUFFIX = ""
sys.modules['sentinel_config'] = mock_sentinel_config
sys.modules['medallion_trainer'] = MagicMock()
sys.modules['git_arctic'] = MagicMock()
sys.modules['xgboost'] = MagicMock()

import vectorbt_researcher_mcp
from vectorbt_researcher_mcp import (
    run_parameter_sweep,
    _fetch_mt5_data,
    _get_model_predictions,
    _run_cv_backtest,
    _evaluate_robustness
)

def test_fetch_mt5_data():
    # Patch specifically where it's used in the module
    with patch('vectorbt_researcher_mcp.mt5.initialize', return_value=True), \
         patch('vectorbt_researcher_mcp.mt5.copy_rates_from_pos', return_value=[(0,0,0,0,1.1), (0,0,0,0,1.2)]):
        price = _fetch_mt5_data("EURUSD")
        assert isinstance(price, pd.Series)
        assert len(price) == 2
        assert price.iloc[0] == 1.1

def test_get_model_predictions():
    mock_model = MagicMock()
    mock_model.predict_proba.return_value = np.array([[0.4, 0.6]] * 10)

    with patch('xgboost.XGBClassifier', return_value=mock_model), \
         patch('os.path.exists', return_value=True):
        price = pd.Series([1.1] * 10)
        probs = _get_model_predictions(price)
        assert len(probs) == 10
        assert probs[0] == 0.6

def test_run_cv_backtest():
    price = pd.Series(np.random.randn(100))
    probs = np.random.rand(100)

    mock_pkf = MagicMock()
    mock_pkf.split.return_value = [(np.arange(80), np.arange(80, 100))]

    mock_pf = MagicMock()
    mock_pf.sharpe_ratio.return_value = pd.Series([1.5])

    # Patch vbt in the module
    with patch('vectorbt_researcher_mcp.vbt.Portfolio.from_signals', return_value=mock_pf):
        all_path_sharpes, last_pf = _run_cv_backtest(price, probs, mock_pkf)
        assert len(all_path_sharpes) == 1
        # Use return_value comparison if Series matching is tricky with mocks
        assert all_path_sharpes[0].iloc[0] == 1.5
        assert last_pf == mock_pf

def test_evaluate_robustness():
    all_path_sharpes = [pd.Series([1.5], index=[0])]
    price = pd.Series(np.random.randn(100))

    mock_pf = MagicMock()
    mock_pf.returns.return_value = pd.Series(np.random.randn(100) * 0.01)

    best_idx, best_sharpe_lb, dsr_conf, n_trials, expected_max = _evaluate_robustness(
        all_path_sharpes, len(price), mock_pf
    )

    assert best_idx == 0
    assert best_sharpe_lb == 1.5
    assert isinstance(dsr_conf, (float, np.float64))
    assert n_trials == 1

def test_run_parameter_sweep_full_flow():
    with patch('vectorbt_researcher_mcp._fetch_mt5_data', return_value=pd.Series([1.1]*100)), \
         patch('vectorbt_researcher_mcp._get_model_predictions', return_value=np.array([0.6]*100)), \
         patch('vectorbt_researcher_mcp._run_cv_backtest') as mock_cv, \
         patch('vectorbt_researcher_mcp._evaluate_robustness') as mock_eval, \
         patch('vectorbt_researcher_mcp._save_to_arctic'), \
         patch('vectorbt_researcher_mcp.send_research_webhook'):

        mock_cv.return_value = ([pd.Series([1.5])], MagicMock())
        mock_eval.return_value = (0, 1.5, 0.96, 1, 0.1)

        result = run_parameter_sweep("EURUSD")

        assert result["status"] == "success"
        assert result["dsr_conf"] == 0.96
        assert result["best_config"] == "0"
