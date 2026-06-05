import sys
import unittest.mock as mock
from dataclasses import dataclass, field
from typing import Any, Optional

# Mocking modules before importing the target
mt5_mock = mock.MagicMock()
sys.modules['MetaTrader5'] = mt5_mock

tp_mock = mock.MagicMock()
sys.modules['tp_placement_engine'] = tp_mock

sys.modules['git_arctic'] = mock.MagicMock()
sys.modules['gitagent_utils'] = mock.MagicMock()

risk_agent_mock = mock.MagicMock()
sys.modules['agents.risk_agent'] = risk_agent_mock

# Mocking check_upcoming_tier1_events
risk_agent_mock.check_upcoming_tier1_events.return_value = (False, "")

mt5_mock.symbol_info.return_value = None

import pytest
from profit_manager_v28_34 import compute_exit_score, PositionState, ExitSignal

@pytest.fixture
def base_ps():
    return PositionState(
        ticket=123,
        symbol="EURUSD",
        direction=0, # BUY
        entry_price=1.1000,
        entry_time=1000,
        entry_atr=0.0100
    )

@pytest.fixture
def base_oracle():
    return {"hmm_state": "BULL"}

def test_crypto_stagnation(base_ps, base_oracle):
    base_ps.symbol = "BTCUSD"
    base_ps.zone2_done = False

    # 121 candles > 120
    sig = compute_exit_score(
        ps=base_ps, oracle=base_oracle, current_price=1.1100, macro_atr=0.0100,
        sl_mult=2.0, live_p=0.8, config={}, sentiment=0.0,
        broker_now=1000, h1_candles=121, is_weekend_pause=False
    )

    assert sig.hard_exit is True
    assert "[STAGNATION LIQUIDATION]" in sig.reason_primary

def test_crypto_thesis_decay(base_ps, base_oracle):
    base_ps.symbol = "ETHUSD"
    base_ps.direction = 0 # BUY

    # live_p 0.5 < 0.55
    sig = compute_exit_score(
        ps=base_ps, oracle=base_oracle, current_price=1.1100, macro_atr=0.0100,
        sl_mult=2.0, live_p=0.5, config={}, sentiment=0.0,
        broker_now=1000, h1_candles=10, is_weekend_pause=False
    )

    assert sig.hard_exit is True
    assert "[THESIS DECAY] Conviction < 0.55" in sig.reason_primary

def test_failsafe_sl_trigger(base_ps, base_oracle):
    # BUY at 1.1000, ATR=0.01, sl_mult=2.0 -> SL at 1.0800
    # Buffer is 10% of ATR = 0.0010. Trigger at 1.0790
    sig = compute_exit_score(
        ps=base_ps, oracle=base_oracle, current_price=1.0780, macro_atr=0.0100,
        sl_mult=2.0, live_p=0.8, config={}, sentiment=0.0,
        broker_now=1000, h1_candles=10, is_weekend_pause=False
    )

    assert sig.hard_exit is True
    assert "[FAILSAFE TRIGGERED]" in sig.reason_primary

def test_macro_shock(base_ps, base_oracle):
    # BUY, sentiment -0.7 < -0.65
    sig = compute_exit_score(
        ps=base_ps, oracle=base_oracle, current_price=1.1100, macro_atr=0.0100,
        sl_mult=2.0, live_p=0.8, config={}, sentiment=-0.7,
        broker_now=1000, h1_candles=10, is_weekend_pause=False
    )

    assert sig.hard_exit is True
    assert "[MACRO SHOCK]" in sig.reason_primary

def test_scored_regime_conflict(base_ps, base_oracle):
    # BUY, HMM=BEAR -> conflict
    base_oracle["hmm_state"] = "BEAR"
    base_ps.regime_conflict_count = 2

    # Needs 3 counts at 0 profit_r
    sig = compute_exit_score(
        ps=base_ps, oracle=base_oracle, current_price=1.1000, macro_atr=0.0100,
        sl_mult=2.0, live_p=0.8, config={}, sentiment=0.0,
        broker_now=3000, h1_candles=10, is_weekend_pause=False
    )

    assert sig.hard_exit is False
    assert sig.score > 0
    assert base_ps.regime_conflict_count == 3

def test_hysteresis_suppression(base_ps, base_oracle):
    # BUY, HMM=BEAR -> score > 0
    base_oracle["hmm_state"] = "BEAR"

    # elapsed < 1200 (3000 - 2000 = 1000)
    sig = compute_exit_score(
        ps=base_ps, oracle=base_oracle, current_price=1.1000, macro_atr=0.0100,
        sl_mult=2.0, live_p=0.8, config={}, sentiment=0.0,
        broker_now=2000, h1_candles=10, is_weekend_pause=False
    )

    assert sig.score == 0
    assert "SUPPRESSED_HARD_HOLD" in sig.reasons[0]

def test_event_horizon_suppression(base_ps, base_oracle):
    base_oracle["hmm_state"] = "BEAR"
    risk_agent_mock.check_upcoming_tier1_events.return_value = (True, "FOMC")

    # elapsed 2000 > 1200
    sig = compute_exit_score(
        ps=base_ps, oracle=base_oracle, current_price=1.1000, macro_atr=0.0100,
        sl_mult=2.0, live_p=0.8, config={}, sentiment=0.0,
        broker_now=4000, h1_candles=10, is_weekend_pause=False
    )

    assert sig.score == 0
    assert "SUPPRESSED_PRE_EVENT" in sig.reasons[0]
    risk_agent_mock.check_upcoming_tier1_events.return_value = (False, "")

def test_profit_dampening(base_ps, base_oracle):
    base_oracle["hmm_state"] = "BEAR"
    base_ps.regime_conflict_count = 10 # ensure score

    # To test dampening, I'll use a current_price that is exactly 2.1R, and make sure TP is far enough.
    # Let's say entry_price=1.1000, macro_atr=0.01, sl_mult=2.0 -> risk=0.02.
    # 2.025R profit -> price = 1.1000 + 2.025 * 0.02 = 1.1405.

    sig = compute_exit_score(
        ps=base_ps, oracle=base_oracle, current_price=1.1405, macro_atr=0.0100,
        sl_mult=2.0, live_p=0.8, config={}, sentiment=0.0,
        broker_now=4000, h1_candles=10, is_weekend_pause=False
    )

    assert sig.hard_exit is False
    assert 0 < sig.score < 0.4
