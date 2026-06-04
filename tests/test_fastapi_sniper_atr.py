import sys
from unittest import mock
import math

# Mocking MetaTrader5 before importing fastapi_sniper
mock_mt5 = mock.Mock()
sys.modules["MetaTrader5"] = mock_mt5

# Mock agents.risk_agent
mock_risk_agent = mock.Mock()
sys.modules["agents"] = mock.Mock()
sys.modules["agents.risk_agent"] = mock_risk_agent

import fastapi_sniper

def test_get_structural_multiplier():
    assert fastapi_sniper.get_structural_multiplier("EURUSD") == 6.0
    assert fastapi_sniper.get_structural_multiplier("BTCUSD") == 4.0
    assert fastapi_sniper.get_structural_multiplier("NAS100") == 4.0
    assert fastapi_sniper.get_structural_multiplier("XAUUSD") == 4.0

def test_calculate_kelly_lot_unified_atr():
    symbol = "EURUSD"
    conviction = 0.8

    mock_info = mock.Mock()
    mock_info.digits = 5
    mock_info.point = 0.00001
    mock_info.trade_tick_value = 1.0
    mock_info.trade_tick_size = 0.00001
    mock_info.volume_step = 0.01
    mock_info.volume_min = 0.01
    mock_info.volume_max = 100.0
    mock_mt5.symbol_info.return_value = mock_info

    mock_tick = mock.Mock()
    mock_tick.ask = 1.1000
    mock_tick.bid = 1.0999
    mock_tick.bid_volume = 10.0
    mock_tick.ask_volume = 10.0
    mock_mt5.symbol_info_tick.return_value = mock_tick

    mock_acc = mock.Mock()
    mock_acc.equity = 10000.0
    mock_acc.balance = 10000.0

    with mock.patch("fastapi_sniper.get_cached_account_info", return_value=mock_acc),          mock.patch("fastapi_sniper.calculate_structural_atr_d1", return_value=0.0020),          mock.patch("fastapi_sniper.get_structural_multiplier", return_value=6.0),          mock.patch("agents.risk_agent.calculate_volatility_scalar", return_value=1.0):

        lot = fastapi_sniper.calculate_kelly_lot(symbol, conviction)
        assert lot > 0
        assert lot == 0.08
