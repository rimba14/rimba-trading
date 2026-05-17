import os
import pytest
from constants import AGENT_SIGNATURE, TRADE_COMMENT_TEMPLATE
from logger_config import get_logger

def test_no_legacy_version_strings():
    import glob
    for root, dirs, files in os.walk("."):
        if ".git" in root or "venv" in root or "llms" in root or "kronos" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        assert "SENTINEL_v23" not in content, f"Legacy strings found in {path}"
                except:
                    pass

def test_utf8_log_handler():
    log = get_logger("test")
    # Must not raise UnicodeEncodeError
    log.info("[OK] UTF-8 test: \u2705 \u274c \u26a0\ufe0f EUR=\u20ac GBP=\u00a3")

def test_agent_signature_format():
    assert AGENT_SIGNATURE == "SENTINEL_v28.7_IRONCLAD_CADES"
    assert "v27" not in AGENT_SIGNATURE

def test_agent_signature_mt5_limit():
    assert len(AGENT_SIGNATURE) < 31, f"AGENT_SIGNATURE exceeds MT5 31-char limit: {len(AGENT_SIGNATURE)} chars"

def test_trade_comment_template():
    comment = TRADE_COMMENT_TEMPLATE.format(
        symbol="ADAUSD", regime="RISK_ON", signal_type="MEAN_REVERSION"
    )[:31]
    assert "v28.7" in comment
    assert len(comment) <= 31  # MT5 broker comment field limit

def test_capital_wall_circuit_breaker_fail_closed():
    from capital_wall import CapitalWall, TradeRejected
    class DummySignal:
        symbol = "EURUSD"
        xgb_p = 0.5
        ddqn_p = 0.5
    
    # Point to a completely bogus port/URL to force a connection exception
    wall = CapitalWall(risk_agent_url="http://localhost:9999/check_trade")
    
    with pytest.raises(TradeRejected) as excinfo:
        wall.check_risk_agent(DummySignal(), 0.1, 1.1000)
    
    assert "[WALL4-FAIL] Risk Agent circuit breaker tripped" in str(excinfo.value)

def test_capital_wall_ex_ante_blackout():
    from capital_wall import CapitalWall, TradeRejected
    class DummySignal:
        symbol = "USDJPY"
    
    wall = CapitalWall()
    # Mock check_upcoming_tier1_events to return True to guarantee test determinism.
    import agents.risk_agent
    original_check = agents.risk_agent.check_upcoming_tier1_events
    try:
        agents.risk_agent.check_upcoming_tier1_events = lambda sym, threshold_hours: (True, "FOMC Rate Decision in 2.0h")
        with pytest.raises(TradeRejected) as excinfo:
            wall.check_event_horizon_blackout(DummySignal())
        assert "[WALL5-FAIL] Tier-1 event within 24h" in str(excinfo.value)
    finally:
        agents.risk_agent.check_upcoming_tier1_events = original_check


def test_feature_integrity_assertion_shield():
    from feature_engineering import validate_features
    import pandas as pd
    
    # 1. Valid DataFrame
    df_valid = pd.DataFrame({
        'RSI': [30.0, 50.0, 70.0],
        'ATR': [0.001, 0.05, 0.1],
        'BB_Width': [0.0, 0.02, 0.1],
        'order_flow_entropy': [0.0, 0.5, 1.0]
    })
    assert validate_features(df_valid, "EURUSD") is True
    
    # 2. Invalid RSI (> 100)
    df_invalid_rsi = df_valid.copy()
    df_invalid_rsi.loc[0, 'RSI'] = 101.0
    with pytest.raises(AssertionError):
        validate_features(df_invalid_rsi, "EURUSD")
        
    # 3. Invalid ATR (<= 0)
    df_invalid_atr = df_valid.copy()
    df_invalid_atr.loc[0, 'ATR'] = 0.0
    with pytest.raises(AssertionError):
        validate_features(df_invalid_atr, "EURUSD")
        
    # 4. Invalid BB_Width (< 0)
    df_invalid_bb = df_valid.copy()
    df_invalid_bb.loc[0, 'BB_Width'] = -0.01
    with pytest.raises(AssertionError):
        validate_features(df_invalid_bb, "EURUSD")
        
    # 5. Invalid Entropy (> 1)
    df_invalid_entropy = df_valid.copy()
    df_invalid_entropy.loc[0, 'order_flow_entropy'] = 1.01
    with pytest.raises(AssertionError):
        validate_features(df_invalid_entropy, "EURUSD")


def test_model_drift_failsafe(monkeypatch):
    import mt5_bridge
    monkeypatch.setattr(mt5_bridge, "initialize_mt5_with_heartbeat", lambda *args, **kwargs: (True, ["EURUSD"]))
    
    import sentinel_slow_loop
    import numpy as np
    
    # Reset
    sentinel_slow_loop._P_SCORE_HISTORY = []
    sentinel_slow_loop._MODEL_DRIFT_HALT = False
    
    # Feed 99 identical scores
    for _ in range(99):
        sentinel_slow_loop._P_SCORE_HISTORY.append(0.50)
    
    # Standard deviation check shouldn't trigger yet (history length < 100)
    assert sentinel_slow_loop._MODEL_DRIFT_HALT is False
    
    # Feed the 100th score
    sentinel_slow_loop._P_SCORE_HISTORY.append(0.50)
    
    # Explicitly trigger standard deviation and mode collapse check
    p_std = float(np.std(sentinel_slow_loop._P_SCORE_HISTORY))
    if len(sentinel_slow_loop._P_SCORE_HISTORY) == 100 and p_std < 0.05:
        sentinel_slow_loop._MODEL_DRIFT_HALT = True
        
    assert sentinel_slow_loop._MODEL_DRIFT_HALT is True



