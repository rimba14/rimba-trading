import sys; import os; sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from unittest.mock import MagicMock

# Mock MetaTrader5 for Linux/non-Windows environments
try:
    import MetaTrader5
except ImportError:
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = True
    mock_mt5.terminal_info.return_value = MagicMock(connected=True, trade_allowed=True)
    mock_mt5.account_info.return_value = MagicMock(balance=10000.0, equity=10000.0, margin=0.0, login=123456, server="MockServer", company="MockBroker")
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.ORDER_TYPE_SELL = 1
    mock_mt5.TRADE_ACTION_DEAL = 1
    mock_mt5.TRADE_RETCODE_DONE = 10009
    mock_mt5.SYMBOL_CHART_MODE_BID = 0
    mock_mt5.TIMEFRAME_D1 = 1440
    mock_mt5.TIMEFRAME_H1 = 60
    mock_mt5.TIMEFRAME_M15 = 15
    sys.modules["MetaTrader5"] = mock_mt5

# Mock arcticdb if not present
try:
    import arcticdb
except ImportError:
    sys.modules["arcticdb"] = MagicMock()
