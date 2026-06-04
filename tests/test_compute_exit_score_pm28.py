import sys
import unittest.mock as mock
from dataclasses import dataclass, field

# Mocking MetaTrader5
mt5_mock = mock.MagicMock()
mt5_mock.ORDER_TYPE_BUY = 0
mt5_mock.ORDER_TYPE_SELL = 1
sys.modules['MetaTrader5'] = mt5_mock

# Mocking check_upcoming_tier1_events
risk_agent_mock = mock.MagicMock()
sys.modules['agents.risk_agent'] = risk_agent_mock

# Now import the function to test
from profit_manager_v28_34 import compute_exit_score, PositionState, ExitSignal

def test_crypto_stagnation_exit():
    ps = PositionState(ticket=1, symbol="BTCUSD", direction=0, entry_price=50000.0, entry_time=1000)
    ps.zone2_done = False
    oracle = {"hmm_state": "BULL"}
    # h1_candles > 120
    sig = compute_exit_score(
        ps=ps, oracle=oracle, current_price=51000.0, macro_atr=1000.0, sl_mult=2.0,
        live_p=0.8, config={}, sentiment=0.0, broker_now=2000, h1_candles=121, is_weekend_pause=False
    )
    assert sig.hard_exit is True
    assert "[STAGNATION LIQUIDATION]" in sig.reason_primary

def test_crypto_thesis_decay_exit():
    ps = PositionState(ticket=1, symbol="BTCUSD", direction=0, entry_price=50000.0, entry_time=1000)
    oracle = {"hmm_state": "BULL"}
    # live_p (conviction) < 0.55
    sig = compute_exit_score(
        ps=ps, oracle=oracle, current_price=51000.0, macro_atr=1000.0, sl_mult=2.0,
        live_p=0.54, config={}, sentiment=0.0, broker_now=2000, h1_candles=10, is_weekend_pause=False
    )
    assert sig.hard_exit is True
    assert "[THESIS DECAY]" in sig.reason_primary

def test_failsafe_sl_trigger():
    ps = PositionState(ticket=1, symbol="EURUSD", direction=0, entry_price=1.1000, entry_time=1000)
    ps.initial_sl = 1.0800
    oracle = {"hmm_state": "NEUTRAL"}
    # buffer = macro_atr * 0.10 = 0.0010
    # current_price <= (sl_target - buffer) = 1.0800 - 0.0010 = 1.0790
    sig = compute_exit_score(
        ps=ps, oracle=oracle, current_price=1.0789, macro_atr=0.0100, sl_mult=2.0,
        live_p=0.6, config={}, sentiment=0.0, broker_now=2000, h1_candles=10, is_weekend_pause=False
    )
    assert sig.hard_exit is True
    assert "[FAILSAFE TRIGGERED]" in sig.reason_primary

def test_macro_shock_sentiment():
    ps = PositionState(ticket=1, symbol="EURUSD", direction=0, entry_price=1.1000, entry_time=1000)
    oracle = {"hmm_state": "NEUTRAL"}
    # sentiment < -0.65 for BUY
    sig = compute_exit_score(
        ps=ps, oracle=oracle, current_price=1.1050, macro_atr=0.0100, sl_mult=2.0,
        live_p=0.6, config={}, sentiment=-0.66, broker_now=2000, h1_candles=10, is_weekend_pause=False
    )
    assert sig.hard_exit is True
    assert "[MACRO SHOCK]" in sig.reason_primary

def test_soft_regime_conflict():
    ps = PositionState(ticket=1, symbol="EURUSD", direction=0, entry_price=1.1000, entry_time=1000)
    oracle = {"hmm_state": "BEAR"} # Conflict for BUY
    # 1200s passed to avoid Suppression
    # profit_r = (1.1050 - 1.1000) / (0.0100 * 2.0) = 0.0050 / 0.0200 = 0.25R
    # r_gate = max(3, 3+0) = 3
    # persistence = 1 / 3 = 0.333
    # score += 0.4 * 0.333 = 0.133
    risk_agent_mock.check_upcoming_tier1_events.return_value = (False, "")
    mt5_mock.symbol_info.return_value = None # to avoid min_edge suppression

    sig = compute_exit_score(
        ps=ps, oracle=oracle, current_price=1.1050, macro_atr=0.0100, sl_mult=2.0,
        live_p=0.6, config={}, sentiment=0.0, broker_now=3000, h1_candles=10, is_weekend_pause=False
    )
    assert sig.score > 0
    assert "REGIME" in sig.reasons[0]
