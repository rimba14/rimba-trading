import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock MetaTrader5 and Arctic before importing the module under test
mock_mt5 = MagicMock()
sys.modules['MetaTrader5'] = mock_mt5
mock_arctic = MagicMock()
sys.modules['arcticdb'] = mock_arctic

import pandas as pd
import execute_highest_conviction as ehc

class TestExecuteHighestConviction(unittest.TestCase):

    @patch('execute_highest_conviction.Arctic')
    def test_get_oracle_candidates(self, mock_arctic_class):
        mock_lib = MagicMock()
        mock_arctic_class.return_value.__getitem__.return_value = mock_lib

        mock_lib.list_symbols.return_value = ["EURUSD_meta", "BTCUSD_meta", "INVALID"]

        # Mock data for EURUSD_meta
        df_eur = pd.DataFrame({
            "meta_conviction": [0.6],
            "wasserstein_state": ["TREND"]
        })
        # Mock data for BTCUSD_meta
        df_btc = pd.DataFrame({
            "xgb_p": [0.2], # SELL conviction 0.8
            "wasserstein_state": ["RANGE"]
        })

        def mock_read(sym):
            mock_data = MagicMock()
            if sym == "EURUSD_meta":
                mock_data.data = df_eur
            elif sym == "BTCUSD_meta":
                mock_data.data = df_btc
            return mock_data

        mock_lib.read.side_effect = mock_read

        candidates = ehc.get_oracle_candidates("mock_url", "mock_lib")

        self.assertEqual(len(candidates), 2)
        # BTC should be first due to higher conviction (0.8 vs 0.6)
        self.assertEqual(candidates[0]["symbol"], "BTCUSD")
        self.assertEqual(candidates[0]["direction"], "SELL")
        self.assertEqual(candidates[0]["conviction"], 0.8)

        self.assertEqual(candidates[1]["symbol"], "EURUSD")
        self.assertEqual(candidates[1]["direction"], "BUY")
        self.assertEqual(candidates[1]["conviction"], 0.6)

    @patch('execute_highest_conviction.mt5')
    def test_calculate_atr(self, mock_mt5_local):
        # Mock rates: (time, open, high, low, close, tick_volume, spread, real_volume)
        mock_rates = [
            (0, 1.1000, 1.1010, 1.0990, 1.1005, 100, 10, 0),
            (0, 1.1005, 1.1020, 1.1000, 1.1015, 100, 10, 0),
        ]
        mock_mt5_local.copy_rates_from_pos.return_value = mock_rates

        # TR1 = max(1.1020-1.1000, |1.1020-1.1005|, |1.1000-1.1005|)
        # TR1 = max(0.0020, 0.0015, 0.0005) = 0.0020
        # ATR = 0.0020 / 1 = 0.0020

        atr = ehc.calculate_atr("EURUSD", 0, 2)
        self.assertAlmostEqual(atr, 0.0020)

    def test_get_trade_parameters_multipliers(self):
        mock_info = MagicMock()
        mock_info.digits = 5
        mock_tick = MagicMock()
        mock_tick.ask = 1.1000
        mock_tick.bid = 1.0998 # spread 0.0002

        # Test default multiplier (6.0)
        sl, tp, price = ehc.get_trade_parameters("EURUSD", "BUY", 0.0010, mock_tick, mock_info)
        # sl = 1.1000 - (0.0010 * 6) = 1.0940
        # tp = 1.1000 + (0.0010 * 6 * 1.5) = 1.1090
        self.assertEqual(sl, 1.0940)
        self.assertEqual(tp, 1.1090)

        # Test Crypto multiplier (4.0)
        sl, tp, price = ehc.get_trade_parameters("BTCUSD", "BUY", 100.0, mock_tick, mock_info)
        # sl = 1.1000 - 400 = -398.9
        self.assertEqual(sl, round(1.1000 - 400.0, 5))

    def test_get_trade_parameters_spread_protection(self):
        mock_info = MagicMock()
        mock_info.digits = 5
        mock_tick = MagicMock()
        mock_tick.ask = 1.1000
        mock_tick.bid = 1.0990 # spread 0.0010

        # ATR very small, so SL dist would be small
        atr = 0.0001
        # default SL dist = 0.0001 * 6 = 0.0006
        # min SL dist = 0.0010 * 1.5 = 0.0015

        sl, tp, price = ehc.get_trade_parameters("EURUSD", "BUY", atr, mock_tick, mock_info)

        # SL should be padded to price - 0.0015 = 1.0985
        # TP should be price + 0.0015 * 1.5 = 1.10225
        self.assertEqual(sl, 1.0985)
        self.assertAlmostEqual(tp, 1.10225)

    def test_calculate_lot_size(self):
        mock_acc = MagicMock()
        mock_acc.balance = 10000

        mock_sym_info = MagicMock()
        mock_sym_info.point = 0.0001
        mock_sym_info.trade_tick_value = 1.0
        mock_sym_info.trade_tick_size = 0.0001
        mock_sym_info.volume_step = 0.01
        mock_sym_info.volume_min = 0.01
        mock_sym_info.volume_max = 100.0

        price = 1.1000
        sl = 1.0900 # 100 points

        # risk_usd = 10000 * 0.02 * 0.5 = 100
        # sl_dist_points = 0.0100 / 0.0001 = 100
        # point_val = 1.0 / (0.0001 / 0.0001) = 1.0
        # raw_lot = 100 / (100 * 1) = 1.0

        lot = ehc.calculate_lot_size("EURUSD", price, sl, mock_acc, mock_sym_info)
        self.assertEqual(lot, 1.0)

    @patch('execute_highest_conviction.mt5')
    def test_send_order_with_retries_success(self, mock_mt5_local):
        mock_res = MagicMock()
        mock_res.retcode = ehc.mt5.TRADE_RETCODE_DONE
        mock_mt5_local.order_send.return_value = mock_res

        req = {"symbol": "EURUSD"}
        result = ehc.send_order_with_retries(req)

        self.assertEqual(result, mock_res)
        mock_mt5_local.order_send.assert_called_once_with(req)

    @patch('execute_highest_conviction.mt5')
    def test_send_order_with_retries_fail_then_success(self, mock_mt5_local):
        mock_fail = MagicMock()
        mock_fail.retcode = 10030 # Invalid fill mode

        mock_success = MagicMock()
        mock_success.retcode = ehc.mt5.TRADE_RETCODE_DONE

        mock_mt5_local.order_send.side_effect = [mock_fail, mock_success]

        req = {"symbol": "EURUSD", "type_filling": "IOC"}
        result = ehc.send_order_with_retries(req)

        self.assertEqual(result, mock_success)
        self.assertEqual(mock_mt5_local.order_send.call_count, 2)

    @patch('execute_highest_conviction.mt5')
    @patch('execute_highest_conviction.get_oracle_candidates')
    @patch('execute_highest_conviction.calculate_atr')
    @patch('execute_highest_conviction.get_trade_parameters')
    @patch('execute_highest_conviction.calculate_lot_size')
    @patch('execute_highest_conviction.send_order_with_retries')
    def test_main_executes_one_trade(self, mock_send, mock_lot, mock_params, mock_atr, mock_candidates, mock_mt5_local):
        mock_mt5_local.initialize.return_value = True
        mock_candidates.return_value = [
            {"symbol": "SYM1", "direction": "BUY", "conviction": 0.9},
            {"symbol": "SYM2", "direction": "BUY", "conviction": 0.8}
        ]
        mock_mt5_local.account_info.return_value = MagicMock()
        mock_mt5_local.symbol_select.return_value = True
        mock_mt5_local.symbol_info.return_value = MagicMock(trade_mode=1)
        mock_mt5_local.symbol_info_tick.return_value = MagicMock()
        mock_mt5_local.positions_get.return_value = None
        mock_atr.return_value = 0.0010
        mock_params.return_value = (1.09, 1.11, 1.10)
        mock_lot.return_value = 0.1

        mock_success = MagicMock()
        mock_success.retcode = ehc.mt5.TRADE_RETCODE_DONE
        mock_send.return_value = mock_success

        # main() doesn't call sys.exit(1) on success.
        # It calls mt5.shutdown() then exits normally.
        ehc.main()

        mock_send.assert_called_once() # Only called for SYM1
        self.assertEqual(mock_send.call_args[0][0]["symbol"], "SYM1")

if __name__ == '__main__':
    unittest.main()
