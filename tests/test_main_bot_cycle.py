import sys
import os
from unittest.mock import MagicMock, patch

# COMPLETELY mock MetaTrader5 BEFORE anything else
sys.modules['MetaTrader5'] = MagicMock()

import pytest

# Mocking environment and dependencies before importing main.py to avoid failures
# due to missing environment variables or network calls during module initialization.

mock_env = {
    "HYPER_LIQUID_KEY": "0x" + "1" * 64
}

# We need to mock the agents before main.py imports them
with patch.dict(os.environ, mock_env), \
     patch('eth_account.Account.from_key') as mock_account_from_key, \
     patch('agents.risk_agent.RiskAgent') as mock_risk_cls, \
     patch('agents.strategy_agent.StrategyAgent') as mock_strat_cls, \
     patch('agents.trading_agent.TradingAgent') as mock_trad_cls, \
     patch('nice_funcs_hyperliquid.get_position'):

    mock_acc = MagicMock()
    mock_acc.address = "0xMockAddress"
    mock_account_from_key.return_value = mock_acc

    # These will be the instances created at module level in main.py
    mock_risk_inst = mock_risk_cls.return_value
    mock_strat_inst = mock_strat_cls.return_value
    mock_trad_inst = mock_trad_cls.return_value

    import main

@pytest.fixture
def mock_n(mocker):
    return mocker.patch('main.n')

@pytest.fixture
def mock_risk_agent():
    return mock_risk_inst

@pytest.fixture
def mock_strategy_agent():
    return mock_strat_inst

@pytest.fixture
def mock_trading_agent():
    return mock_trad_inst

def test_bot_cycle_in_position(mock_n):
    """Test that bot_cycle closes position and returns early if already in a position."""
    # Setup: Already in position
    mock_n.get_position.return_value = {"in_pos": True, "long": True, "pnl_pct": 2.5}

    main.bot_cycle()

    # Assertions
    mock_n.get_position.assert_called_with(main.SYMBOL, main.ACCOUNT_ADDRESS)
    mock_n.pnl_close.assert_called_with(main.SYMBOL, main.TAKE_PROFIT_PCT, main.STOP_LOSS_PCT, main.account)
    # Ensure entry logic (cancel_all_orders) was skipped
    mock_n.cancel_all_orders.assert_not_called()

def test_bot_cycle_no_signal(mock_n, mock_strategy_agent):
    """Test that bot_cycle does nothing if there is no technical signal."""
    # Reset mocks for this test
    mock_n.reset_mock()
    mock_strategy_agent.reset_mock()

    # Setup: Not in position, HOLD signal
    mock_n.get_position.return_value = {"in_pos": False}
    mock_strategy_agent.run.return_value = ("HOLD", "No signal")

    main.bot_cycle()

    # Assertions
    mock_n.cancel_all_orders.assert_called_once_with(main.account)
    mock_strategy_agent.run.assert_called_once()
    mock_n.limit_order.assert_not_called()

def test_bot_cycle_risk_blocked(mock_n, mock_strategy_agent, mock_risk_agent):
    """Test that bot_cycle aborts if RiskAgent blocks the trade."""
    mock_n.reset_mock()
    mock_strategy_agent.reset_mock()
    mock_risk_agent.reset_mock()

    # Setup: BUY signal but risk blocked
    mock_n.get_position.return_value = {"in_pos": False}
    mock_strategy_agent.run.return_value = ("BUY", "Strong trend")
    mock_risk_agent.check_trade.return_value = (False, "Too much risk")

    main.bot_cycle()

    # Assertions
    mock_risk_agent.check_trade.assert_called_once_with(main.SYMBOL, main.POSITION_SIZE_USD, main.LEVERAGE)
    mock_n.get_ohlcv.assert_not_called()
    mock_n.limit_order.assert_not_called()

def test_bot_cycle_ai_dissent(mock_n, mock_strategy_agent, mock_risk_agent, mock_trading_agent):
    """Test that bot_cycle aborts if TradingAgent (AI) disagrees with the technical signal."""
    mock_n.reset_mock()
    mock_strategy_agent.reset_mock()
    mock_risk_agent.reset_mock()
    mock_trading_agent.reset_mock()

    # Setup: BUY signal, risk allowed, but AI says HOLD
    mock_n.get_position.return_value = {"in_pos": False}
    mock_strategy_agent.run.return_value = ("BUY", "Strong trend")
    mock_risk_agent.check_trade.return_value = (True, "Risk OK")
    mock_n.get_ohlcv.return_value = MagicMock()
    mock_trading_agent.analyze.return_value = {"decision": "HOLD", "confidence": 0.1, "reasoning": "Market choppy"}

    main.bot_cycle()

    # Assertions
    mock_trading_agent.analyze.assert_called_once()
    mock_n.limit_order.assert_not_called()

def test_bot_cycle_successful_buy(mock_n, mock_strategy_agent, mock_risk_agent, mock_trading_agent):
    """Test a full successful BUY trade execution cycle."""
    mock_n.reset_mock()
    mock_strategy_agent.reset_mock()
    mock_risk_agent.reset_mock()
    mock_trading_agent.reset_mock()

    # Setup: Everything aligned for BUY
    mock_n.get_position.return_value = {"in_pos": False}
    mock_strategy_agent.run.return_value = ("BUY", "Strong trend")
    mock_risk_agent.check_trade.return_value = (True, "Risk OK")
    mock_n.get_ohlcv.return_value = MagicMock()
    mock_trading_agent.analyze.return_value = {"decision": "BUY", "confidence": 0.9, "reasoning": "Moon soon"}
    mock_n.ask_bid.return_value = (100.0, 99.0) # ask, bid
    mock_n.adjust_leverage_usd_size.return_value = (5, 0.1) # leverage, size

    main.bot_cycle()

    # Assertions
    mock_n.ask_bid.assert_called_once_with(main.SYMBOL)
    mock_n.limit_order.assert_called_once_with(
        main.SYMBOL, True, 0.1, 99.0, False, main.account
    )

def test_bot_cycle_successful_sell(mock_n, mock_strategy_agent, mock_risk_agent, mock_trading_agent):
    """Test a full successful SELL trade execution cycle."""
    mock_n.reset_mock()
    mock_strategy_agent.reset_mock()
    mock_risk_agent.reset_mock()
    mock_trading_agent.reset_mock()

    # Setup: Everything aligned for SELL
    mock_n.get_position.return_value = {"in_pos": False}
    mock_strategy_agent.run.return_value = ("SELL", "Weak trend")
    mock_risk_agent.check_trade.return_value = (True, "Risk OK")
    mock_n.get_ohlcv.return_value = MagicMock()
    mock_trading_agent.analyze.return_value = {"decision": "SELL", "confidence": 0.85, "reasoning": "Crash imminent"}
    mock_n.ask_bid.return_value = (101.0, 100.0) # ask, bid
    mock_n.adjust_leverage_usd_size.return_value = (5, 0.2) # leverage, size

    main.bot_cycle()

    # Assertions
    mock_n.ask_bid.assert_called_once_with(main.SYMBOL)
    # is_buy should be False for SELL signal
    mock_n.limit_order.assert_called_once_with(
        main.SYMBOL, False, 0.2, 101.0, False, main.account
    )
