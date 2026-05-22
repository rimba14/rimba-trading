import json
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

# Mock the entire vectorbt dependency since it's large and complex
# The function imports vectorbt internally, so we need to mock it in sys.modules
import sys
mock_vbt = MagicMock()
sys.modules['vectorbt'] = mock_vbt

from agents.vectorbt_researcher_mcp import run_parameter_sweep

def test_run_parameter_sweep_success_with_webhook():
    """Test happy path where Sharpe ratio > 1.2 triggers webhook."""

    # Setup mock portfolio and its return values
    mock_pf = MagicMock()

    # Mock sharpe_ratio() to return a mock series with idxmax() and max()
    mock_sharpe = MagicMock()
    mock_sharpe.idxmax.return_value = "(20, 100)"
    mock_sharpe.max.return_value = 1.5  # > 1.2 to trigger webhook
    mock_pf.sharpe_ratio.return_value = mock_sharpe

    # Mock total_return() to return a mock object with max()
    mock_total_return = MagicMock()
    mock_total_return.max.return_value = 0.25
    mock_pf.total_return.return_value = mock_total_return

    # Link mock portfolio to vbt.Portfolio.from_signals
    mock_vbt.Portfolio.from_signals.return_value = mock_pf

    # Need to also patch the send_research_webhook to ensure it is called
    with patch('agents.vectorbt_researcher_mcp.send_research_webhook') as mock_webhook:
        # Run the function
        result_json = run_parameter_sweep("EURUSD", "M15", 30)

        # Verify JSON response
        result = json.loads(result_json)
        assert result["status"] == "success"
        assert result["best_config"] == "(20, 100)"
        assert result["sharpe_ratio"] == 1.5
        assert result["total_return"] == 0.25

        # Verify webhook was called
        mock_webhook.assert_called_once_with("EURUSD", "(20, 100)", 1.5, 0.25)

def test_run_parameter_sweep_success_no_webhook():
    """Test happy path where Sharpe ratio <= 1.2 does not trigger webhook."""

    # Setup mock portfolio and its return values
    mock_pf = MagicMock()

    # Mock sharpe_ratio() to return a mock series with idxmax() and max()
    mock_sharpe = MagicMock()
    mock_sharpe.idxmax.return_value = "(10, 50)"
    mock_sharpe.max.return_value = 1.0  # <= 1.2 to NOT trigger webhook
    mock_pf.sharpe_ratio.return_value = mock_sharpe

    # Mock total_return() to return a mock object with max()
    mock_total_return = MagicMock()
    mock_total_return.max.return_value = 0.10
    mock_pf.total_return.return_value = mock_total_return

    # Link mock portfolio to vbt.Portfolio.from_signals
    mock_vbt.Portfolio.from_signals.return_value = mock_pf

    with patch('agents.vectorbt_researcher_mcp.send_research_webhook') as mock_webhook:
        # Run the function
        result_json = run_parameter_sweep("GBPUSD", "H1", 60)

        # Verify JSON response
        result = json.loads(result_json)
        assert result["status"] == "success"
        assert result["best_config"] == "(10, 50)"
        assert result["sharpe_ratio"] == 1.0
        assert result["total_return"] == 0.10

        # Verify webhook was NOT called
        mock_webhook.assert_not_called()

def test_run_parameter_sweep_error():
    """Test error path where an exception is caught and returned."""

    # Make vbt.Portfolio.from_signals raise an Exception
    mock_vbt.Portfolio.from_signals.side_effect = Exception("Mock Error")

    # Run the function
    result_json = run_parameter_sweep("JPYUSD", "M5", 10)

    # Verify JSON response
    result = json.loads(result_json)
    assert result["status"] == "error"
    assert result["message"] == "Mock Error"

    # Reset side effect for other tests
    mock_vbt.Portfolio.from_signals.side_effect = None
