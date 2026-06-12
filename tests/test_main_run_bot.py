import sys
import pytest
from unittest.mock import MagicMock, patch

# Mock MetaTrader5 before importing main to avoid ImportError on Linux
sys.modules['MetaTrader5'] = MagicMock()

import main

def test_run_bot_logic():
    """
    Test the run_bot entry point.
    It should:
    1. Call initialize() if ACCOUNT_ADDRESS is None
    2. Call bot_cycle() once immediately
    3. Schedule bot_cycle() every 1 minute
    4. Enter a loop that calls schedule.run_pending()
    """
    with patch('main.initialize') as mock_init, \
         patch('main.bot_cycle') as mock_bot_cycle, \
         patch('main.schedule.every') as mock_every, \
         patch('main.schedule.run_pending') as mock_run_pending, \
         patch('main.time.sleep') as mock_sleep:

        # Setup mock for schedule.every(1).minutes.do(bot_cycle)
        mock_minutes = MagicMock()
        mock_every.return_value.minutes = mock_minutes

        # Break the infinite loop on the first time.sleep(1) call
        mock_sleep.side_effect = InterruptedError("Stop infinite loop for testing")

        # Trigger run_bot
        with pytest.raises(InterruptedError, match="Stop infinite loop for testing"):
            main.run_bot()

        # 1. Verify initialize was called (since ACCOUNT_ADDRESS starts as None)
        mock_init.assert_called_once()

        # 2. Verify bot_cycle was called once immediately
        mock_bot_cycle.assert_called_once()

        # 3. Verify scheduling was set up
        mock_every.assert_called_with(1)
        mock_minutes.do.assert_called_with(main.bot_cycle)

        # 4. Verify loop behavior
        mock_run_pending.assert_called()
        mock_sleep.assert_called_with(1)

def test_bot_cycle_not_initialized():
    """Tests that bot_cycle exits early if agents are not initialized."""
    with patch('main.risk_agent', None), \
         patch('main.strategy_agent', None), \
         patch('builtins.print') as mock_print:

        main.bot_cycle()
        mock_print.assert_any_call("[ERROR] Agents not initialized. Call initialize() first.")

def test_bot_cycle_in_position():
    """Tests that bot_cycle skips entry logic if already in a position."""
    # Mock agents and account to simulate initialized state
    mock_risk = MagicMock()
    mock_strat = MagicMock()
    mock_trade = MagicMock()
    mock_acc = MagicMock()

    with patch('main.risk_agent', mock_risk), \
         patch('main.strategy_agent', mock_strat), \
         patch('main.trading_agent', mock_trade), \
         patch('main.account', mock_acc), \
         patch('main.ACCOUNT_ADDRESS', "0x123"), \
         patch('nice_funcs_hyperliquid.get_position') as mock_get_pos, \
         patch('nice_funcs_hyperliquid.pnl_close') as mock_pnl_close:

        # Simulate being in a position
        mock_get_pos.return_value = {"in_pos": True, "long": True, "pnl_pct": 2.5}

        main.bot_cycle()

        mock_pnl_close.assert_called_once()
        # Ensure strategy_agent.run() was NOT called
        mock_strat.run.assert_not_called()
