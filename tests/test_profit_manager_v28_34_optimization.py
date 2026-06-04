import os
import sys
from unittest import mock

# Mocking dependencies before importing anything that uses them
mt5_mock = mock.MagicMock()
mt5_mock.ORDER_TYPE_BUY = 0
mt5_mock.ORDER_TYPE_SELL = 1
sys.modules['MetaTrader5'] = mt5_mock
sys.modules['MetaTrader5.constants'] = mock.MagicMock()

import pytest
import numpy as np

# Adjust path and import profit_manager
sys.path.insert(0, os.getcwd())
import profit_manager_v28_34 as pm

class MockPosition:
    def __init__(self, ticket, symbol, type_, price_open, sl=0.0, tp=0.0, volume=0.01, profit=10.0, time=123456, magic=142):
        self.ticket = ticket
        self.symbol = symbol
        self.type = type_
        self.price_open = price_open
        self.sl = sl
        self.tp = tp
        self.volume = volume
        self.profit = profit
        self.time = time
        self.magic = magic
        self.price_current = price_open + (0.0010 if type_ == 0 else -0.0010)

def get_mock_symbol_info(symbol):
    m = mock.Mock()
    m.digits = 5
    m.trade_contract_size = 100000.0
    m.volume_step = 0.01
    m.volume_min = 0.01
    m.trade_stops_level = 10
    m.point = 0.00001
    m.spread = 2
    m.trade_tick_size = 0.00001
    return m

def test_profit_manager_audit_caching():
    # Test that _audit_positions works with our new caching
    manager = pm.SentinelProfitManager()

    mock_positions = [
        MockPosition(101, "EURUSD", 0, 1.1000),
        MockPosition(102, "EURUSD", 0, 1.1005)
    ]

    mock_tick = mock.Mock()
    mock_tick.bid = 1.1010
    mock_tick.ask = 1.1011
    mock_tick.time = 123456789

    mock_info = get_mock_symbol_info("EURUSD")

    with mock.patch("profit_manager_v28_34.mt5.symbol_info_tick", return_value=mock_tick) as mock_mt5_tick, \
         mock.patch("profit_manager_v28_34.mt5.symbol_info", return_value=mock_info) as mock_mt5_info, \
         mock.patch("profit_manager_v28_34.calculate_atr_d1", return_value=0.0050) as mock_atr, \
         mock.patch("profit_manager_v28_34.get_equity_drawdown", return_value=(0.01, 10000.0)), \
         mock.patch("profit_manager_v28_34.get_atr_multipliers", return_value=(2.0, 4.0)), \
         mock.patch.object(manager, "_get_state") as mock_get_state:

        ps_mock = mock.Mock()
        ps_mock.liquidation_sent = False
        ps_mock.entry_atr = 0.0
        ps_mock.is_buy.return_value = True
        ps_mock.profit_r.return_value = 1.0
        ps_mock.entry_time = 123456000
        ps_mock.entry_tf = "H1"
        ps_mock.current_conviction = 0.8
        ps_mock.peak_price = 0.0
        ps_mock.peak_profit_r = 0.0
        mock_get_state.return_value = ps_mock

        manager._oracle = mock.Mock()
        manager._oracle.get.return_value = {"hmm_state": "TREND", "atr": 0.0050, "strategy_type": "MOMENTUM"}

        pm.REGIME_POLL_INTERVAL = 0

        manager._audit_positions(mock_positions, {})

        # Check that MT5 calls were cached (called once for 2 positions of the same symbol)
        assert mock_mt5_tick.call_count == 1
        assert mock_mt5_info.call_count == 1
        assert mock_atr.call_count == 1

def test_naked_sweep_caching():
    manager = pm.SentinelProfitManager()
    pos = MockPosition(103, "GBPUSD", 0, 1.2500, sl=0.0, tp=0.0)

    mock_tick = mock.Mock()
    mock_tick.bid = 1.2505
    mock_tick.ask = 1.2506

    mock_info = get_mock_symbol_info("GBPUSD")

    with mock.patch("profit_manager_v28_34.mt5.symbol_info_tick", return_value=mock_tick) as mock_mt5_tick, \
         mock.patch("profit_manager_v28_34.mt5.symbol_info", return_value=mock_info) as mock_mt5_info, \
         mock.patch("profit_manager_v28_34.calculate_atr_d1", return_value=0.0050) as mock_atr, \
         mock.patch("profit_manager_v28_34.get_safe_atr", side_effect=pm.get_safe_atr) as mock_safe_atr, \
         mock.patch("profit_manager_v28_34.calculate_institutional_hard_stop", return_value=1.2400), \
         mock.patch("profit_manager_v28_34.get_atr_multipliers", return_value=(2.0, 4.0)), \
         mock.patch("profit_manager_v28_34.normalize_stop", side_effect=lambda s,c,v,**k: v), \
         mock.patch("profit_manager_v28_34.mt5.order_send") as mock_send:

        manager._oracle = mock.Mock()
        manager._oracle.get.return_value = {"hmm_state": "TREND", "atr": 0.0050}

        # Call with pre-fetched data
        manager._naked_sweep(pos, info=mock_info, tick=mock_tick, d1_atr=0.0050)

        # Should NOT call MT5 again
        assert mock_mt5_tick.call_count == 0
        assert mock_mt5_info.call_count == 0

        # Verify get_safe_atr was called with passed info/tick/d1_atr
        mock_safe_atr.assert_called_once()
        _, kwargs = mock_safe_atr.call_args
        assert kwargs['info'] == mock_info
        assert kwargs['tick'] == mock_tick
        assert kwargs['d1_atr'] == 0.0050
