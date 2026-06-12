import sys
import pytest
from unittest.mock import MagicMock, patch

# Mock MetaTrader5 before importing RiskAgent
mock_mt5 = MagicMock()
sys.modules['MetaTrader5'] = mock_mt5

from agents.risk_agent import RiskAgent

@pytest.fixture
def risk_agent():
    return RiskAgent()

@pytest.fixture
def mock_mt5_funcs():
    with patch('agents.risk_agent.mt5') as m:
        m.initialize.return_value = True

        # Default account info
        mock_acc = MagicMock()
        mock_acc.equity = 10000.0
        m.account_info.return_value = mock_acc

        # Default symbol info
        mock_info = MagicMock()
        mock_info.volume_min = 0.01
        mock_info.trade_tick_value = 1.0
        mock_info.trade_tick_size = 0.00001
        mock_info.point = 0.00001
        mock_info.ask = 1.1000
        mock_info.trade_contract_size = 100000.0
        # Use simple floats for swap to avoid MagicMock formatting issues
        mock_info.swap_long = -5.0
        mock_info.swap_short = -2.0
        m.symbol_info.return_value = mock_info

        # Default rates
        m.copy_rates_from_pos.return_value = [
            {'high': 1.1010, 'low': 1.1000},
            {'high': 1.1020, 'low': 1.1010}
        ]

        # Default positions
        m.positions_get.return_value = []

        yield m

@pytest.fixture(autouse=True)
def mock_macro_calendar():
    with patch('agents.risk_agent.check_upcoming_tier1_events') as mock_macro:
        mock_macro.return_value = (False, "")
        yield mock_macro

def test_check_trade_success(risk_agent, mock_mt5_funcs):
    """Test happy path where all checks pass."""
    success, reason = risk_agent.check_trade("EURUSD", 1000.0, 10.0, 0.5, 0.5)
    assert success is True
    assert "Risk check passed" in reason

def test_check_trade_circuit_breaker(risk_agent):
    """Test circuit breaker veto."""
    risk_agent.circuit_breaker_active = True
    success, reason = risk_agent.check_trade("EURUSD", 1000.0, 10.0)
    assert success is False
    assert "Circuit breaker active" in reason

def test_check_trade_zero_sizing(risk_agent):
    """Test zero-sizing veto."""
    success, reason = risk_agent.check_trade("EURUSD", 0.0, 10.0)
    assert success is False
    assert "[ZERO_SIZING_VETO]" in reason

def test_check_trade_mt5_init_failure(risk_agent, mock_mt5_funcs):
    """Test MT5 initialization failure."""
    mock_mt5_funcs.initialize.return_value = False
    success, reason = risk_agent.check_trade("EURUSD", 1000.0, 10.0)
    assert success is False
    assert "MT5 connection failure" in reason

def test_check_trade_leverage_limit(risk_agent, mock_mt5_funcs):
    """Test leverage limit violation."""
    risk_agent.max_leverage = 20
    success, reason = risk_agent.check_trade("EURUSD", 1000.0, 25.0)
    assert success is False
    assert "exceeds max allowed 20x" in reason

def test_check_trade_position_size_limit(risk_agent, mock_mt5_funcs):
    """Test single position size limit violation."""
    risk_agent.max_position_size_usd = 5000.0
    success, reason = risk_agent.check_trade("EURUSD", 6000.0, 10.0)
    assert success is False
    assert "exceeds cap $5000.0" in reason

def test_check_trade_affordability_veto(risk_agent, mock_mt5_funcs):
    """Test affordability veto for indices/metals/crypto."""
    # Mock BTCUSD with high ATR and low equity to trigger veto
    mock_acc = MagicMock()
    mock_acc.equity = 100.0 # Very low equity
    mock_mt5_funcs.account_info.return_value = mock_acc

    mock_info = MagicMock()
    mock_info.volume_min = 1.0 # High min volume
    mock_info.trade_tick_value = 1.0
    mock_info.trade_tick_size = 1.0
    mock_info.point = 1.0
    mock_info.ask = 50000.0
    mock_info.swap_long = -5.0
    mock_info.swap_short = -2.0
    mock_mt5_funcs.symbol_info.return_value = mock_info

    mock_mt5_funcs.copy_rates_from_pos.return_value = [
        {'high': 51000.0, 'low': 50000.0} # ATR = 1000
    ]

    success, reason = risk_agent.check_trade("BTCUSD", 100.0, 1.0)
    assert success is False
    assert "[AFFORDABILITY_VETO]" in reason

def test_check_trade_cognitive_dissonance(risk_agent, mock_mt5_funcs):
    """Test cognitive dissonance veto."""
    # XGB=0.8, DDQN=0.2 => dissonance = 0.6 > 0.55
    success, reason = risk_agent.check_trade("EURUSD", 1000.0, 10.0, xgb_p=0.8, ddqn_p=0.2)
    assert success is False
    assert "Cognitive Dissonance Exceeded" in reason

def test_check_trade_cumulative_exposure(risk_agent, mock_mt5_funcs):
    """Test cumulative symbol exposure limit violation."""
    risk_agent.max_symbol_exposure_usd = 10000.0

    mock_pos = MagicMock()
    mock_pos.symbol = "EURUSD"
    mock_pos.volume = 0.08
    mock_pos.price_open = 100000.0 # 8000.0 notional

    mock_mt5_funcs.positions_get.return_value = [mock_pos]

    # Existing 8000 + new 3000 = 11000 > 10000
    success, reason = risk_agent.check_trade("EURUSD", 3000.0, 10.0)
    assert success is False
    assert "Cumulative Exposure Cap Reached" in reason

def test_check_trade_portfolio_heat_veto(risk_agent, mock_mt5_funcs):
    """Test portfolio heat veto (currency correlation cap)."""
    risk_agent.max_currency_heat_pct = 0.01 # 1% limit
    # equity is 10000, so limit is 100 USD risk

    with patch('agents.risk_agent.calculate_currency_exposure') as mock_calc:
        mock_calc.return_value = {"EUR": 96.0}

        # New trade EURUSD size 2000.0
        # sl_dist = 0.0030 (based on mock ATR 0.0010)
        # new_risk_usd = (0.0030 / 1.1000) * 2000.0 = 5.45
        # Total EUR risk = 96.0 + 5.45 = 101.45 > 100.0
        success, reason = risk_agent.check_trade("EURUSD", 2000.0, 10.0, xgb_p=0.7) # Direction BUY

        assert success is False
        assert "[PORTFOLIO_HEAT_VETO]" in reason
        assert "EUR" in reason

def test_check_trade_macro_blackout(risk_agent, mock_mt5_funcs):
    """Test ex-ante macro blackout veto."""
    # Override the autouse mock for this specific test
    with patch('agents.risk_agent.check_upcoming_tier1_events') as mock_macro:
        mock_macro.return_value = (True, "FOMC Rate Decision in 2.0h")

        success, reason = risk_agent.check_trade("EURUSD", 1000.0, 10.0)
        assert success is False
        assert "Ex-Ante Macro Blackout" in reason
        assert "FOMC Rate Decision" in reason
