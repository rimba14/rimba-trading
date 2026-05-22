import pytest
from unittest.mock import MagicMock, patch
import sys

# Mock dependencies before importing
sys.modules['MetaTrader5'] = MagicMock()
sys.modules['git_arctic'] = MagicMock()

from agents.profit_manager_v15 import run_profit_manager
import agents.profit_manager_v15 as pm

@patch('agents.profit_manager_v15.mt5')
@patch('agents.profit_manager_v15.logging')
def test_run_profit_manager_init_failure(mock_logging, mock_mt5):
    mock_mt5.initialize.return_value = False

    run_profit_manager()

    mock_logging.error.assert_called_with('MT5 Init Failed')
