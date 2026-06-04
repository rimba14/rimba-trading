import sys
import unittest.mock as mock
import pytest
from dataclasses import dataclass, field
from typing import Any

# Mock MetaTrader5
mt5_mock = mock.MagicMock()
mt5_mock.ORDER_TYPE_BUY = 0
mt5_mock.ORDER_TYPE_SELL = 1
mt5_mock.symbol_info.return_value = None # Default to None to avoid complex mocks in compute_exit_score
sys.modules['MetaTrader5'] = mt5_mock

# Mock other dependencies
sys.modules['tp_placement_engine'] = mock.MagicMock()
sys.modules['git_arctic'] = mock.MagicMock()
sys.modules['gitagent_utils'] = mock.MagicMock()
sys.modules['gitagent_types'] = mock.MagicMock()
sys.modules['arcticdb'] = mock.MagicMock()
sys.modules['filelock'] = mock.MagicMock()

# Mock agents.risk_agent
risk_agent_mock = mock.MagicMock()
sys.modules['agents.risk_agent'] = risk_agent_mock

from profit_manager_v28_34 import (
    PositionState, ExitSignal, compute_exit_score,
    _check_crypto_exits, _check_failsafe_exits, _check_macro_exits
)

@pytest.fixture
def base_ps():
    return PositionState(
        ticket=123,
        symbol="EURUSD",
        direction=0, # BUY
        entry_price=1.1000,
        entry_time=1000,
        initial_sl=1.0900
    )

@pytest.fixture
def base_ps_old():
    # age > 1200s to avoid HARD_HOLD
    return PositionState(
        ticket=123,
        symbol="EURUSD",
        direction=0, # BUY
        entry_price=1.1000,
        entry_time=1000,
        initial_sl=1.0900
    )

@pytest.fixture
def crypto_ps():
    return PositionState(
        ticket=456,
        symbol="BTCUSD",
        direction=0, # BUY
        entry_price=60000.0,
        entry_time=1000,
        initial_sl=58000.0
    )

@pytest.fixture
def base_oracle():
    return {"hmm_state": "NEUTRAL", "atr": 0.0010}

@pytest.fixture
def base_config():
    return {}

def test_crypto_stagnation_exit(crypto_ps):
    sig = ExitSignal()
    # h1_candles > 120 and not ps.zone2_done
    triggered = _check_crypto_exits(
        crypto_ps, "BTCUSD", True, "BULL", "BUY", 121, 0.8, sig
    )
    assert triggered is True
    assert sig.hard_exit is True
    assert "[STAGNATION LIQUIDATION]" in sig.reason_primary

def test_crypto_thesis_decay_exit(crypto_ps):
    sig = ExitSignal()
    # thesis_p_crypto < 0.55
    # live_p = 0.5 for BUY -> thesis_p = 0.5 < 0.55
    triggered = _check_crypto_exits(
        crypto_ps, "BTCUSD", True, "BULL", "BUY", 10, 0.5, sig
    )
    assert triggered is True
    assert sig.hard_exit is True
    assert "[THESIS DECAY] Conviction < 0.55" in sig.reason_primary

def test_crypto_regime_inversion_exit(crypto_ps):
    sig = ExitSignal()
    # (is_buy and hmm == "BEAR") for 3 periods
    for _ in range(2):
        triggered = _check_crypto_exits(
            crypto_ps, "BTCUSD", True, "BEAR", "BUY", 10, 0.8, sig
        )
        assert triggered is False
        assert sig.hard_exit is False

    triggered = _check_crypto_exits(
        crypto_ps, "BTCUSD", True, "BEAR", "BUY", 10, 0.8, sig
    )
    assert triggered is True
    assert sig.hard_exit is True
    assert "[THESIS DECAY] Regime Inversion" in sig.reason_primary

def test_failsafe_sl_breach(base_ps):
    sig = ExitSignal()
    # SL = 1.0900. Buffer = 0.0010 * 0.1 = 0.0001. Breach = 1.0900 - 0.0001 = 1.0899
    triggered = _check_failsafe_exits(
        base_ps, 1.0898, True, 0.0010, 10.0, sig
    )
    assert triggered is True
    assert sig.hard_exit is True
    assert "[FAILSAFE TRIGGERED]" in sig.reason_primary

def test_macro_shock_exit():
    sig = ExitSignal()
    triggered = _check_macro_exits("BUY", -0.7, sig)
    assert triggered is True
    assert sig.hard_exit is True
    assert "[MACRO SHOCK]" in sig.reason_primary

def test_regime_conflict_scoring(base_ps_old, base_oracle, base_config):
    # pos_dir = "BUY", hmm = "BEAR"
    base_oracle["hmm_state"] = "BEAR"

    # broker_now = 2500 -> elapsed = 1500 > 1200
    sig = compute_exit_score(
        base_ps_old, base_oracle, 1.1000, 0.0010, 10.0, 0.8, base_config, 0.0, 2500, 10, False
    )

    assert sig.score > 0
    assert any("REGIME" in r for r in sig.reasons)
    assert base_ps_old.regime_conflict_count == 1

def test_profit_weighted_dampening(base_ps_old, base_oracle, base_config):
    base_oracle["hmm_state"] = "BEAR"
    # profit_r > 2.0
    # profit_delta = 1.1015 - 1.1000 = 0.0015
    # risk = 0.0010 * 0.5 = 0.0005
    # profit_r = 3.0

    # First, get score without dampening (no profit)
    # broker_now = 2500 -> elapsed = 1500 > 1200
    sig_no_damp = compute_exit_score(
        base_ps_old, base_oracle, 1.1000, 0.0010, 10.0, 0.8, base_config, 0.0, 2500, 10, False
    )

    # Reset conflict count for a clean second run
    base_ps_old.regime_conflict_count = 0

    # Now with dampening (price higher, but not hitting failsafe TP)
    # tp_target = 1.1000 + 0.5 * 2.0 * 0.0010 = 1.1010. Wait, TP target depends on sl_mult.
    # sl_mult = 0.5 -> tp_mult = 1.0. tp_target = 1.1000 + 1.0 * 0.0010 = 1.1010
    # Let's use sl_mult=2.0 -> tp_target = 1.1000 + 4.0 * 0.0010 = 1.1040.
    # current_price = 1.1015. profit_delta = 0.0015. risk = 2.0 * 0.0010 = 0.0020. profit_r = 0.75. Not enough dampening.

    # Let's adjust sl_mult and price to get profit_r > 2.0
    # sl_mult = 0.5 -> risk = 0.0005. profit_delta = 0.0015 (at 1.1015). profit_r = 3.0.
    # tp_target = 1.1000 + 2.0 * 0.5 * 0.0010 = 1.1010. 1.1015 blows past TP.

    # Let's use sl_mult=5.0 -> risk = 0.0050. profit_r > 2.0 needs profit_delta > 0.0100.
    # price = 1.1110. tp_target = 1.1000 + 2.0 * 5.0 * 0.0010 = 1.1100. 1.1110 blows past TP.

    # We need a large tp_mult or just a large gap.
    # The failsafe uses sl_mult * 2.0 as tp_mult.
    # dampening uses profit_r which uses macro_atr * sl_mult as risk.

    # If we want profit_r > 2.0 without hitting failsafe:
    # we need current_delta / (atr * sl_mult) > 2.0
    # and current_delta < (atr * sl_mult * 2.0) + buffer
    # These are contradictory if buffer is small.
    # WAIT! profit_r uses the sl_mult PASSED TO IT.
    # failsafe also uses the sl_mult PASSED TO IT.

    # AH! compute_exit_score DESIGN:
    # profit_r = ps.profit_r(current_price, macro_atr, sl_mult)
    # tp_target = (ps.entry_price + sl_mult * 2.0 * macro_atr)

    # So profit_r is always < 2.0 before hitting failsafe TP,
    # UNLESS we have a custom initial_sl or something? No.

    # Wait, the code for dampening is:
    # if profit_r > 2.0 and sig.score > 0:

    # But failsafe is:
    # if (is_buy and current_price >= (tp_target + buffer))
    # where tp_target = entry + sl_mult * 2.0 * macro_atr

    # So profit_r = delta / (macro_atr * sl_mult).
    # If profit_r > 2.0, then delta / (macro_atr * sl_mult) > 2.0 => delta > 2.0 * macro_atr * sl_mult.
    # This means delta > tp_target - entry.
    # So delta + entry > tp_target => current_price > tp_target.

    # Thus, scored dampening for profit_r > 2.0 is only reached if the failsafe doesn't trigger.
    # The failsafe triggers at tp_target + buffer.
    # So if tp_target < current_price < tp_target + buffer, we might see it.

    # Or, we can mock ps.profit_r to return what we want.
    with mock.patch.object(base_ps_old, 'profit_r', return_value=3.0):
        sig_damp = compute_exit_score(
            base_ps_old, base_oracle, 1.1005, 0.0010, 10.0, 0.8, base_config, 0.0, 2500, 10, False
        )

    assert sig_damp.score < sig_no_damp.score
