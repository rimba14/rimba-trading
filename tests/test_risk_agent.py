import sys
from unittest.mock import MagicMock
sys.modules['MetaTrader5'] = MagicMock()

import pytest
from agents.risk_agent import RiskAgent

def test_circuit_breaker():
    agent = RiskAgent()
    agent.circuit_breaker_active = True
    allowed, reason = agent.check_trade("EURUSD", 1000.0, 10.0)
    assert not allowed
    assert "Circuit breaker active" in reason

def test_zero_sizing():
    agent = RiskAgent()
    allowed, reason = agent.check_trade("EURUSD", 0.0, 10.0)
    assert not allowed
    assert "[ZERO_SIZING_VETO]" in reason

def test_mt5_init_failure(monkeypatch):
    import agents.risk_agent
    monkeypatch.setattr(agents.risk_agent.mt5, "initialize", lambda: False)
    agent = RiskAgent()
    allowed, reason = agent.check_trade("EURUSD", 1000.0, 10.0)
    assert not allowed
    assert "MT5 connection failure" in reason

def test_affordability_veto(monkeypatch):
    import agents.risk_agent
    # Need to setup mt5 mocks for affordability check
    monkeypatch.setattr(agents.risk_agent.mt5, "initialize", lambda: True)

    mock_info = MagicMock()
    mock_info.trade_tick_value = 100000.0
    mock_info.trade_tick_size = 0.0001
    mock_info.point = 0.0001
    mock_info.volume_min = 0.5
    mock_info.ask = 1000.0
    mock_info.swap_long = 1.0
    mock_info.swap_short = 1.0
    monkeypatch.setattr(agents.risk_agent, "check_upcoming_tier1_events", lambda s, **kwargs: (False, ""))
    monkeypatch.setattr(agents.risk_agent.mt5, "symbol_info", lambda s: mock_info)

    mock_acc = MagicMock()
    mock_acc.equity = 1000.0
    monkeypatch.setattr(agents.risk_agent.mt5, "account_info", lambda: mock_acc)

    rates = [{'high': 1.1000, 'low': 1.0900}] * 20
    monkeypatch.setattr(agents.risk_agent.mt5, "copy_rates_from_pos", lambda *args: rates)

    agent = RiskAgent()
    # Indices/Metals/Crypto logic check
    allowed, reason = agent.check_trade("BTCUSD", 1000.0, 10.0)
    assert not allowed
    assert "[AFFORDABILITY_VETO]" in reason

def test_cognitive_dissonance(monkeypatch):
    import agents.risk_agent
    monkeypatch.setattr(agents.risk_agent.mt5, "initialize", lambda: True)
    monkeypatch.setattr(agents.risk_agent.mt5, "symbol_info", lambda s: None)
    monkeypatch.setattr(agents.risk_agent.mt5, "account_info", lambda: None)

    agent = RiskAgent()
    allowed, reason = agent.check_trade("EURUSD", 1000.0, 10.0, xgb_p=0.9, ddqn_p=0.2)
    assert not allowed
    assert "Cognitive Dissonance Exceeded" in reason


def test_leverage_limit(monkeypatch):
    import agents.risk_agent
    monkeypatch.setattr(agents.risk_agent.mt5, "initialize", lambda: True)
    monkeypatch.setattr(agents.risk_agent.mt5, "symbol_info", lambda s: None)
    monkeypatch.setattr(agents.risk_agent.mt5, "account_info", lambda: None)

    agent = RiskAgent()
    agent.max_leverage = 5.0
    allowed, reason = agent.check_trade("EURUSD", 1000.0, 10.0)
    assert not allowed
    assert "Leverage 10.0x exceeds max allowed" in reason

def test_max_position_size(monkeypatch):
    import agents.risk_agent
    monkeypatch.setattr(agents.risk_agent.mt5, "initialize", lambda: True)
    monkeypatch.setattr(agents.risk_agent.mt5, "symbol_info", lambda s: None)
    monkeypatch.setattr(agents.risk_agent.mt5, "account_info", lambda: None)

    agent = RiskAgent()
    agent.max_position_size_usd = 500.0
    allowed, reason = agent.check_trade("EURUSD", 1000.0, 2.0)
    assert not allowed
    assert "exceeds cap" in reason

def test_cumulative_exposure(monkeypatch):
    import agents.risk_agent
    monkeypatch.setattr(agents.risk_agent.mt5, "initialize", lambda: True)
    monkeypatch.setattr(agents.risk_agent.mt5, "symbol_info", lambda s: None)
    monkeypatch.setattr(agents.risk_agent.mt5, "account_info", lambda: None)

    mock_pos1 = MagicMock()
    mock_pos1.symbol = "EURUSD"
    mock_pos1.volume = 1.0
    mock_pos1.price_open = 10000.0

    monkeypatch.setattr(agents.risk_agent.mt5, "positions_get", lambda: [mock_pos1])

    agent = RiskAgent()
    agent.max_symbol_exposure_usd = 5000.0
    allowed, reason = agent.check_trade("EURUSD", 1000.0, 2.0)
    assert not allowed
    assert "Cumulative Exposure Cap Reached" in reason

def test_portfolio_heat_veto(monkeypatch):
    import agents.risk_agent
    monkeypatch.setattr(agents.risk_agent.mt5, "initialize", lambda: True)
    monkeypatch.setattr(agents.risk_agent.mt5, "positions_get", lambda: [])

    mock_acc = MagicMock()
    mock_acc.equity = 1000.0
    monkeypatch.setattr(agents.risk_agent.mt5, "account_info", lambda: mock_acc)

    monkeypatch.setattr(agents.risk_agent, "calculate_currency_exposure", lambda pos: {"EUR": 50.0, "USD": -50.0})
    monkeypatch.setattr(agents.risk_agent, "parse_base_quote", lambda sym: ("EUR", "USD"))

    mock_info = MagicMock()
    mock_info.ask = 1.1000
    mock_info.trade_tick_size = 0.0001
    mock_info.point = 0.0001
    mock_info.trade_tick_value = 100000.0
    monkeypatch.setattr(agents.risk_agent.mt5, "symbol_info", lambda s: mock_info)
    rates = [{'high': 1.1000, 'low': 1.0900}] * 20
    monkeypatch.setattr(agents.risk_agent.mt5, "copy_rates_from_pos", lambda *args: rates)

    agent = RiskAgent()
    agent.max_currency_heat_pct = 0.04 # 40 USD
    # New trade adds risk to EUR, current is 50. Limit is 40.
    allowed, reason = agent.check_trade("EURUSD", 100.0, 2.0)
    assert not allowed
    assert "[PORTFOLIO_HEAT_VETO]" in reason


def test_negative_carry_veto(monkeypatch):
    import agents.risk_agent
    monkeypatch.setattr(agents.risk_agent.mt5, "initialize", lambda: True)
    monkeypatch.setattr(agents.risk_agent.mt5, "positions_get", lambda: [])
    monkeypatch.setattr(agents.risk_agent, "calculate_currency_exposure", lambda pos: {"EUR": 0.0, "USD": 0.0})
    monkeypatch.setattr(agents.risk_agent, "parse_base_quote", lambda sym: ("EUR", "USD"))

    mock_acc = MagicMock()
    mock_acc.equity = 1000.0
    monkeypatch.setattr(agents.risk_agent.mt5, "account_info", lambda: mock_acc)

    mock_info = MagicMock()
    mock_info.ask = 1.1000
    mock_info.trade_tick_size = 0.0001
    mock_info.point = 0.0001
    mock_info.trade_tick_value = 100000.0
    mock_info.swap_long = -50.0 # very negative swap
    monkeypatch.setattr(agents.risk_agent.mt5, "symbol_info", lambda s: mock_info)

    # ATR = 0.01
    rates = [{'high': 1.1000, 'low': 1.0900}] * 20
    monkeypatch.setattr(agents.risk_agent.mt5, "copy_rates_from_pos", lambda *args: rates)
    monkeypatch.setattr(agents.risk_agent, "check_upcoming_tier1_events", lambda s, **kwargs: (False, ""))

    agent = RiskAgent()
    allowed, reason = agent.check_trade("EURUSD", 100.0, 2.0, xgb_p=0.9, ddqn_p=0.9) # BUY
    assert not allowed
    assert "Negative Carry Veto" in reason

def test_macro_blackout(monkeypatch):
    import agents.risk_agent
    monkeypatch.setattr(agents.risk_agent.mt5, "initialize", lambda: True)
    monkeypatch.setattr(agents.risk_agent.mt5, "positions_get", lambda: [])
    monkeypatch.setattr(agents.risk_agent, "calculate_currency_exposure", lambda pos: {"EUR": 0.0, "USD": 0.0})
    monkeypatch.setattr(agents.risk_agent, "parse_base_quote", lambda sym: ("EUR", "USD"))

    mock_acc = MagicMock()
    mock_acc.equity = 1000.0
    monkeypatch.setattr(agents.risk_agent.mt5, "account_info", lambda: mock_acc)

    mock_info = MagicMock()
    mock_info.ask = 1.1000
    mock_info.trade_tick_size = 0.0001
    mock_info.point = 0.0001
    mock_info.trade_tick_value = 100000.0
    mock_info.swap_long = 1.0
    mock_info.swap_short = 1.0
    monkeypatch.setattr(agents.risk_agent.mt5, "symbol_info", lambda s: mock_info)

    rates = [{'high': 1.1000, 'low': 1.0900}] * 20
    monkeypatch.setattr(agents.risk_agent.mt5, "copy_rates_from_pos", lambda *args: rates)

    monkeypatch.setattr(agents.risk_agent, "check_upcoming_tier1_events", lambda s, **kwargs: (True, "FOMC"))

    agent = RiskAgent()
    allowed, reason = agent.check_trade("EURUSD", 100.0, 2.0, xgb_p=0.9, ddqn_p=0.9)
    assert not allowed
    assert "Ex-Ante Macro Blackout" in reason

def test_happy_path(monkeypatch):
    import agents.risk_agent
    monkeypatch.setattr(agents.risk_agent.mt5, "initialize", lambda: True)
    monkeypatch.setattr(agents.risk_agent.mt5, "positions_get", lambda: [])
    monkeypatch.setattr(agents.risk_agent, "calculate_currency_exposure", lambda pos: {"EUR": 0.0, "USD": 0.0})
    monkeypatch.setattr(agents.risk_agent, "parse_base_quote", lambda sym: ("EUR", "USD"))

    mock_acc = MagicMock()
    mock_acc.equity = 1000.0
    monkeypatch.setattr(agents.risk_agent.mt5, "account_info", lambda: mock_acc)

    mock_info = MagicMock()
    mock_info.ask = 1.1000
    mock_info.trade_tick_size = 0.0001
    mock_info.point = 0.0001
    mock_info.trade_tick_value = 100000.0
    mock_info.swap_long = 1.0
    mock_info.swap_short = 1.0
    monkeypatch.setattr(agents.risk_agent.mt5, "symbol_info", lambda s: mock_info)

    rates = [{'high': 1.1000, 'low': 1.0900}] * 20
    monkeypatch.setattr(agents.risk_agent.mt5, "copy_rates_from_pos", lambda *args: rates)

    monkeypatch.setattr(agents.risk_agent, "check_upcoming_tier1_events", lambda s, **kwargs: (False, ""))

    agent = RiskAgent()
    allowed, reason = agent.check_trade("EURUSD", 100.0, 2.0, xgb_p=0.9, ddqn_p=0.9)
    assert allowed
    assert reason == "Risk check passed."
