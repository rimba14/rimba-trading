import pytest
from unittest.mock import patch

# Mock out git_arctic, MT5, and os modules before importing profit_manager_v15
import sys
from unittest.mock import MagicMock

sys.modules['git_arctic'] = MagicMock()
sys.modules['MetaTrader5'] = MagicMock()
sys.modules['gitagent_utils'] = MagicMock()

import agents.profit_manager_v15 as pm

def test_get_asset_multiplier_forex_usd():
    with patch('agents.profit_manager_v15.utils.get_symbol_regime', return_value='FOREX_USD'):
        assert pm.get_asset_multiplier('EURUSD') == 6.0

def test_get_asset_multiplier_forex_cross():
    with patch('agents.profit_manager_v15.utils.get_symbol_regime', return_value='FOREX_CROSS'):
        assert pm.get_asset_multiplier('EURGBP') == 6.0

def test_get_asset_multiplier_index():
    with patch('agents.profit_manager_v15.utils.get_symbol_regime', return_value='INDEX'):
        assert pm.get_asset_multiplier('SPX500') == 4.0

def test_get_asset_multiplier_commodity():
    with patch('agents.profit_manager_v15.utils.get_symbol_regime', return_value='COMMODITY'):
        assert pm.get_asset_multiplier('XAUUSD') == 4.0

def test_get_asset_multiplier_crypto():
    with patch('agents.profit_manager_v15.utils.get_symbol_regime', return_value='CRYPTO'):
        assert pm.get_asset_multiplier('BTCUSD') == 4.0

def test_get_asset_multiplier_equity():
    with patch('agents.profit_manager_v15.utils.get_symbol_regime', return_value='EQUITY'):
        assert pm.get_asset_multiplier('AAPL') == 3.0

def test_get_asset_multiplier_default():
    with patch('agents.profit_manager_v15.utils.get_symbol_regime', return_value='UNKNOWN'):
        assert pm.get_asset_multiplier('UNKNOWN_SYMBOL') == 4.0
