import pytest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os
import json
import numpy as np
from datetime import datetime

# Mock dependencies before importing the module
mt5_mock = MagicMock()
# Define MT5 constants
mt5_mock.ORDER_TYPE_BUY = 0
mt5_mock.ORDER_TYPE_SELL = 1
mt5_mock.ORDER_TYPE_BUY_LIMIT = 2
mt5_mock.ORDER_TYPE_SELL_LIMIT = 3
mt5_mock.TRADE_ACTION_DEAL = 1
mt5_mock.TRADE_ACTION_PENDING = 5
mt5_mock.ORDER_TIME_GTC = 0
mt5_mock.ORDER_FILLING_IOC = 1
mt5_mock.TIMEFRAME_M15 = 15
mt5_mock.TRADE_RETCODE_DONE = 10009

sys.modules['MetaTrader5'] = mt5_mock
sys.modules['gitagent_utils'] = MagicMock()

# --- HARD MOCK MCP ---
class MockFastMCP:
    def __init__(self, *args, **kwargs):
        pass
    def tool(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator
    def run(self, *args, **kwargs):
        pass

mock_fastmcp_module = MagicMock()
mock_fastmcp_module.FastMCP = MockFastMCP
sys.modules['mcp'] = MagicMock()
sys.modules['mcp.server'] = MagicMock()
sys.modules['mcp.server.fastmcp'] = mock_fastmcp_module

import agents.trade_executor_mcp as te

def test_calculate_kelly_lot_size_happy_path():
    with patch('agents.trade_executor_mcp.get_dynamic_risk_params') as mock_get_params:
        mock_get_params.return_value = {
            "epistemic_gate": 0.82,
            "kelly_fraction": 0.25,
            "virtual_sl_multiplier": None
        }

        lots = te.calculate_kelly_lot_size(
            p=0.6,
            equity=10000.0,
            sl_points=0.01,
            tick_value=1.0,
            tick_size=0.00001,
            point=0.00001
        )
        assert pytest.approx(lots) == 0.2

def test_calculate_kelly_lot_size_sl_zero():
    lots = te.calculate_kelly_lot_size(0.6, 10000.0, 0.0, 1.0, 0.00001, 0.00001)
    assert lots == 0.0

def test_calculate_kelly_lot_size_low_p():
    with patch('agents.trade_executor_mcp.get_dynamic_risk_params') as mock_get_params:
        mock_get_params.return_value = {
            "epistemic_gate": 0.82,
            "kelly_fraction": 0.25,
            "virtual_sl_multiplier": None
        }

        lots = te.calculate_kelly_lot_size(
            p=0.4,
            equity=10000.0,
            sl_points=0.01,
            tick_value=1.0,
            tick_size=0.00001,
            point=0.00001
        )
        assert pytest.approx(lots) == 0.2

def test_calculate_kelly_lot_size_max_risk_cap():
    with patch('agents.trade_executor_mcp.get_dynamic_risk_params') as mock_get_params:
        mock_get_params.return_value = {
            "epistemic_gate": 0.82,
            "kelly_fraction": 1.0,
            "virtual_sl_multiplier": None
        }

        lots = te.calculate_kelly_lot_size(
            p=0.9,
            equity=10000.0,
            sl_points=0.01,
            tick_value=1.0,
            tick_size=0.00001,
            point=0.00001
        )
        assert pytest.approx(lots) == 0.2

def test_calculate_kelly_lot_size_custom_params():
    with patch('agents.trade_executor_mcp.get_dynamic_risk_params') as mock_get_params:
        mock_get_params.return_value = {
            "epistemic_gate": 0.82,
            "kelly_fraction": 0.1,
            "virtual_sl_multiplier": None
        }

        lots = te.calculate_kelly_lot_size(
            p=0.7,
            equity=10000.0,
            sl_points=0.01,
            tick_value=1.0,
            tick_size=0.00001,
            point=0.00001
        )
        assert pytest.approx(lots) == 0.2

def test_calculate_kelly_lot_size_math_variation():
    with patch('agents.trade_executor_mcp.get_dynamic_risk_params') as mock_get_params:
        mock_get_params.return_value = {
            "epistemic_gate": 0.82,
            "kelly_fraction": 0.25,
            "virtual_sl_multiplier": None
        }

        lots = te.calculate_kelly_lot_size(
            p=0.8,
            equity=50000.0,
            sl_points=0.05,
            tick_value=10.0,
            tick_size=0.001,
            point=0.0001
        )
        assert pytest.approx(lots) == 2.0

def test_execute_trade_mt5_init_fail():
    te.mt5.initialize.return_value = False
    result = te.execute_trade("EURUSD", 0.9, "regime_1")
    assert "MT5 Initialization Failed" in result
    te.mt5.initialize.return_value = True

def test_execute_trade_epistemic_gate_rejection():
    with patch('agents.trade_executor_mcp.get_dynamic_risk_params') as mock_params:
        mock_params.return_value = {"epistemic_gate": 0.82, "kelly_fraction": 0.25}
        result = te.execute_trade("EURUSD", 0.6, "regime_1")
        data = json.loads(result)
        assert data["status"] == "REJECTED"
        assert "below 0.820 threshold" in data["reason"]

def test_execute_trade_symbol_not_found():
    te.mt5.symbol_info.return_value = None
    result = te.execute_trade("NONEXISTENT", 0.9, "regime_1")
    assert "Symbol NONEXISTENT not found" in result

def test_execute_trade_amnesia_lock():
    mock_pos = MagicMock()
    mock_pos.magic = 142
    te.mt5.positions_get.return_value = [mock_pos]
    te.mt5.symbol_info.return_value = MagicMock()

    result = te.execute_trade("EURUSD", 0.9, "regime_1")
    data = json.loads(result)
    assert data["status"] == "REJECTED"
    assert "Amnesia Lock" in data["reason"]
    te.mt5.positions_get.return_value = []

def test_execute_trade_portfolio_heat_rejection():
    te.mt5.symbol_info.return_value = MagicMock()
    te.mt5.symbol_info_tick.return_value = MagicMock()
    account_mock = MagicMock()
    account_mock.equity = 10000
    te.mt5.account_info.return_value = account_mock

    pos = MagicMock()
    pos.symbol = "EURUSD"
    pos.magic = 142
    pos.price_open = 1.1000
    pos.sl = 1.0000
    pos.volume = 10.0

    te.mt5.positions_get.side_effect = [[], [pos]]

    sym_info = MagicMock()
    sym_info.point = 0.0001
    sym_info.trade_tick_value = 1.0
    sym_info.trade_tick_size = 0.0001
    te.mt5.symbol_info.return_value = sym_info

    result = te.execute_trade("EURUSD", 0.9, "regime_1")
    data = json.loads(result)
    assert data["status"] == "REJECTED"
    assert "Portfolio Heat > 20%" in data["reason"]
    te.mt5.positions_get.side_effect = None
    te.mt5.positions_get.return_value = []

def test_execute_trade_leverage_wall_rejection():
    te.mt5.symbol_info.return_value = MagicMock()
    te.mt5.symbol_info_tick.return_value = MagicMock()
    account_mock = MagicMock()
    account_mock.equity = 10000
    te.mt5.account_info.return_value = account_mock

    pos = MagicMock()
    pos.symbol = "EURUSD"
    pos.magic = 999
    pos.price_open = 1.0
    pos.volume = 2.0

    te.mt5.positions_get.side_effect = [[], [pos]]

    sym_info = MagicMock()
    sym_info.trade_contract_size = 100000
    te.mt5.symbol_info.return_value = sym_info

    result = te.execute_trade("EURUSD", 0.9, "regime_1")
    data = json.loads(result)
    assert data["status"] == "REJECTED"
    assert "Leverage Wall > 10x" in data["reason"]
    te.mt5.positions_get.side_effect = None
    te.mt5.positions_get.return_value = []

def test_execute_trade_insufficient_data():
    te.mt5.symbol_info.return_value = MagicMock()
    te.mt5.symbol_info_tick.return_value = MagicMock()

    account_mock = MagicMock()
    account_mock.equity = 10000
    te.mt5.account_info.return_value = account_mock
    te.mt5.positions_get.return_value = []

    te.mt5.copy_rates_from_pos.return_value = None
    result = te.execute_trade("EURUSD", 0.9, "regime_1")
    assert "Insufficient M15 data" in result

def test_execute_trade_success():
    te.mt5.initialize.return_value = True

    sym_info = MagicMock()
    sym_info.point = 0.00001
    sym_info.volume_min = 0.01
    sym_info.volume_max = 100.0
    sym_info.volume_step = 0.01
    sym_info.trade_tick_value = 1.0
    sym_info.trade_tick_size = 0.00001
    sym_info.trade_contract_size = 100000
    sym_info.trade_stops_level = 5
    te.mt5.symbol_info.return_value = sym_info

    tick = MagicMock()
    tick.ask = 1.1005
    tick.bid = 1.1000
    te.mt5.symbol_info_tick.return_value = tick

    account = MagicMock()
    account.equity = 10000.0
    te.mt5.account_info.return_value = account

    te.mt5.positions_get.return_value = []

    rates = np.zeros(100, dtype=[('high', '<f8'), ('low', '<f8'), ('close', '<f8')])
    rates['high'] = 1.1010
    rates['low'] = 1.1000
    rates['close'] = 1.1005
    te.mt5.copy_rates_from_pos.return_value = rates

    order_res = MagicMock()
    order_res.retcode = 10009
    order_res.order = 123456
    te.mt5.order_send.return_value = order_res

    with patch('agents.trade_executor_mcp.get_asset_multiplier', return_value=4.0),          patch('agents.trade_executor_mcp.get_dynamic_risk_params', return_value={"epistemic_gate": 0.82, "kelly_fraction": 0.25, "virtual_sl_multiplier": None}),          patch('builtins.open', mock_open()) as mocked_file,          patch('os.path.exists', return_value=True),          patch('agents.trade_executor_mcp.notifier.send_execution_alert') as mock_alert:

        result = te.execute_trade("EURUSD", 0.9, "regime_1")

        data = json.loads(result)
        assert data["status"] == "EXECUTED"
        assert data["symbol"] == "EURUSD"
        assert data["total_lots"] > 0
        assert len(data["grid"]) == 5

        assert te.mt5.order_send.call_count == 5
        mock_alert.assert_called_once()
        mocked_file.assert_called_with("C:/Sentinel_Project/simulated_ledger.csv", "a", encoding='utf-8')
