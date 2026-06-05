import sys
from unittest.mock import MagicMock, patch
import pytest

# Mock MetaTrader5 before importing the module
sys.modules['MetaTrader5'] = MagicMock()
import MetaTrader5 as mt5

import execute_highest_conviction as ehc

@pytest.fixture
def mock_lib():
    lib = MagicMock()
    lib.list_symbols.return_value = ["EURUSD_meta", "BTCUSD_meta"]

    # Mock data for EURUSD
    data_eur = MagicMock()
    data_eur.empty = False
    data_eur.iloc = [None, {"meta_conviction": 0.8, "wasserstein_state": "TREND"}]
    lib.read.return_value.data = data_eur

    return lib

def test_get_candidate_trades(mock_lib):
    candidates = ehc.get_candidate_trades(mock_lib)
    assert len(candidates) == 2
    assert candidates[0]['symbol'] == "EURUSD"
    assert candidates[0]['direction'] == "BUY"
    assert candidates[0]['conviction'] == 0.8

def test_calculate_atr_manual():
    # rates tuple: (time, open, high, low, close, tick_volume, spread, real_volume)
    rates = [
        (0, 1.10, 1.12, 1.09, 1.11, 0, 0, 0),
        (0, 1.11, 1.13, 1.10, 1.12, 0, 0, 0),
    ]
    # TR = max(1.13-1.10, |1.13-1.11|, |1.10-1.11|) = max(0.03, 0.02, 0.01) = 0.03
    atr = ehc.calculate_atr_manual(rates)
    assert pytest.approx(atr) == 0.03

def test_calculate_sl_tp_lot():
    tick = MagicMock()
    tick.ask = 1.1000
    tick.bid = 1.0990

    info = MagicMock()
    info.digits = 5
    info.point = 0.00001
    info.trade_tick_value = 1.0
    info.trade_tick_size = 0.00001
    info.volume_step = 0.01
    info.volume_min = 0.01
    info.volume_max = 100.0

    acc = MagicMock()
    acc.balance = 1000.0

    rates = [
        (0, 1.10, 1.11, 1.09, 1.10, 0, 0, 0),
        (0, 1.10, 1.11, 1.09, 1.10, 0, 0, 0),
    ]
    # ATR = 0.02 (approx)

    with patch('execute_highest_conviction.calculate_atr_manual', return_value=0.01):
        sl, tp, lot = ehc.calculate_sl_tp_lot("EURUSD", "BUY", tick, info, acc, rates)
        assert sl is not None
        assert tp is not None
        assert lot > 0

@patch('MetaTrader5.order_send')
def test_execute_trade_success(mock_order_send):
    mock_result = MagicMock()
    mock_result.retcode = mt5.TRADE_RETCODE_DONE
    mock_order_send.return_value = mock_result

    success = ehc.execute_trade("EURUSD", "BUY", 0.1, 1.1000, 1.0900, 1.1150)
    assert success is True
    assert mock_order_send.called

@patch('MetaTrader5.order_send')
def test_execute_trade_retry(mock_order_send):
    mock_result_fail = MagicMock()
    mock_result_fail.retcode = 10030 # Invalid fill mode
    mock_result_fail.comment = "Invalid fill mode"

    mock_result_success = MagicMock()
    mock_result_success.retcode = mt5.TRADE_RETCODE_DONE

    mock_order_send.side_effect = [mock_result_fail, mock_result_success]

    success = ehc.execute_trade("EURUSD", "BUY", 0.1, 1.1000, 1.0900, 1.1150)
    assert success is True
    assert mock_order_send.call_count == 2
