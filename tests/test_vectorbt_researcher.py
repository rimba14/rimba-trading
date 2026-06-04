import json
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import sys

# Mock dependencies
mock_vbt = MagicMock()
sys.modules['vectorbt'] = mock_vbt
sys.modules["MetaTrader5"] = MagicMock()
sys.modules["gitagent_utils"] = MagicMock()

from agents.vectorbt_researcher_mcp import run_parameter_sweep

def test_run_parameter_sweep_success_with_webhook():
    """Test happy path where Sharpe ratio > 1.2 triggers webhook."""
    mock_pf = MagicMock()
    mock_sharpe = MagicMock()
    mock_sharpe.idxmax.return_value = "(20, 100)"
    mock_sharpe.max.return_value = 1.5
    mock_pf.sharpe_ratio.return_value = mock_sharpe
    mock_total_return = MagicMock()
    mock_total_return.max.return_value = 0.25
    mock_pf.total_return.return_value = mock_total_return
    mock_vbt.Portfolio.from_signals.return_value = mock_pf

    with patch("vectorbt_researcher_mcp._fetch_mt5_data", return_value=pd.Series([100]*100)), \
         patch("vectorbt_researcher_mcp._get_model_predictions", return_value=np.array([0.6]*100)), \
         patch("vectorbt_researcher_mcp._save_to_arctic"), \
         patch('agents.vectorbt_researcher_mcp.send_research_webhook') as mock_webhook:

        result_json = run_parameter_sweep("EURUSD", "M15", 30)
        result = json.loads(result_json)

        assert result["status"] == "success"
        assert result["best_config"] == "0"
        assert result["sharpe_lb"] == 1.0

def test_run_parameter_sweep_success_no_webhook():
    """Test happy path where Sharpe ratio <= 1.2 does not trigger webhook."""
    mock_pf = MagicMock()
    mock_sharpe = MagicMock()
    mock_sharpe.idxmax.return_value = "(10, 50)"
    mock_sharpe.max.return_value = 1.0
    mock_pf.sharpe_ratio.return_value = mock_sharpe
    mock_total_return = MagicMock()
    mock_total_return.max.return_value = 0.10
    mock_pf.total_return.return_value = mock_total_return
    mock_vbt.Portfolio.from_signals.return_value = mock_pf

    with patch("vectorbt_researcher_mcp._fetch_mt5_data", return_value=pd.Series([100]*100)), \
         patch("vectorbt_researcher_mcp._get_model_predictions", return_value=np.array([0.6]*100)), \
         patch("vectorbt_researcher_mcp._save_to_arctic"), \
         patch('agents.vectorbt_researcher_mcp.send_research_webhook') as mock_webhook:

        result_json = run_parameter_sweep("GBPUSD", "H1", 60)
        result = json.loads(result_json)

        assert result["status"] == "success"
        assert result["best_config"] == "0"
        assert result["sharpe_lb"] == 1.0

def test_run_parameter_sweep_error():
    """Test error path where an exception is caught and returned."""
    with patch("vectorbt_researcher_mcp._fetch_mt5_data", side_effect=Exception("Mock Error")):
        result_json = run_parameter_sweep("JPYUSD", "M5", 10)
        result = json.loads(result_json)
        assert result["status"] == "error"
        assert result["message"] == "Mock Error"
