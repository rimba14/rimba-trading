
import pytest
from unittest.mock import MagicMock, patch
import sys
from datetime import datetime
import pytz

# Mock MetaTrader5 before importing pre_execution_gate
mock_mt5 = MagicMock()
sys.modules["MetaTrader5"] = mock_mt5

import pre_execution_gate as peg
from pre_execution_gate import PreExecutionVerdict, GateResult, GateContext, BLOCK, ALLOW

@pytest.fixture
def mocked_mt5():
    mock_mt5.reset_mock()
    mock_mt5.initialize.return_value = True
    return mock_mt5

@pytest.fixture
def mock_cfg():
    with patch("pre_execution_gate.cfg") as mocked:
        mocked.GATE_MIN_EQUITY = {"EURUSD": 100.0}
        mocked.GATE_ECN_MIN_LOTS = {"EURUSD": 0.01}
        mocked.GATE_MAX_LEVERAGE = 30.0
        mocked.GATE_MAX_RISK_PCT_PER_TRADE = 0.02
        mocked.GATE_MAX_PORTFOLIO_HEAT = 0.05
        mocked.GATE_BLACKOUT_FRIDAY_HOUR = 22
        mocked.GATE_BLACKOUT_FRIDAY_MIN = 0
        mocked.GATE_BLACKOUT_MONDAY_HOUR = 0
        mocked.GATE_BLACKOUT_MONDAY_MIN = 0
        yield mocked

# Existing tests for run_all_gates compatibility

def test_gate0_correlation_cluster_limit_pass(mocked_mt5):
    mocked_mt5.positions_get.return_value = []
    mocked_mt5.orders_get.return_value = []

    ctx = GateContext(
        symbol="EURUSD", direction="BUY", asset_class="FOREX", regime="BULL",
        kelly_lots=0.1, entry_price=1.1, sl_distance=0.05, tp_distance=0.15,
        risk_usd=10.0, equity=10000.0, current_heat_usd=0.0, embargo_registry={}
    )
    res = peg.gate0_correlation_cluster_limit(ctx)
    assert res.status == ALLOW
    assert res.gate == "GATE-0"

def test_gate0_global_cap_reached(mocked_mt5):
    # Create 5 mock positions with magic 142
    mock_positions = [MagicMock(magic=142, symbol="EURUSD", type=0) for _ in range(5)]
    mocked_mt5.positions_get.return_value = mock_positions
    mocked_mt5.orders_get.return_value = []

    ctx = GateContext(
        symbol="GBPUSD", direction="BUY", asset_class="FOREX", regime="BULL",
        kelly_lots=0.1, entry_price=1.1, sl_distance=0.05, tp_distance=0.15,
        risk_usd=10.0, equity=10000.0, current_heat_usd=0.0, embargo_registry={}
    )
    res = peg.gate0_correlation_cluster_limit(ctx)
    assert res.status == BLOCK
    assert res.gate == "GATE-0-GLOBAL-CAP"

def test_run_all_gates_pass(mocked_mt5, mock_cfg):
    mocked_mt5.positions_get.return_value = []
    mocked_mt5.orders_get.return_value = []
    mocked_mt5.symbol_info.return_value = MagicMock(trade_contract_size=100000.0)
    # Mock rates for ATR calculation
    mocked_mt5.copy_rates_from_pos.return_value = [
        (0, 1.1, 1.1001, 1.1, 1.1, 0, 0, 0) for _ in range(20)
    ]

    ctx = GateContext(
        symbol="EURUSD",
        direction="BUY",
        asset_class="FOREX",
        regime="BULL",
        kelly_lots=0.1,
        entry_price=1.1,
        sl_distance=0.05,
        tp_distance=0.15,
        risk_usd=10.0,
        equity=10000.0,
        current_heat_usd=0.0,
        embargo_registry={}
    )
    verdict = peg.run_all_gates(ctx, ticket_ref="T1")
    assert verdict.approved
    assert "All 8 gates passed" in verdict.summary()

def test_run_all_gates_fail_gate0(mocked_mt5, mock_cfg):
    # Force Gate 0 failure
    mock_positions = [MagicMock(magic=142, symbol="EURUSD", type=0) for _ in range(5)]
    mocked_mt5.positions_get.return_value = mock_positions
    mocked_mt5.orders_get.return_value = []

    ctx = GateContext(
        symbol="EURUSD",
        direction="BUY",
        asset_class="FOREX",
        regime="BULL",
        kelly_lots=0.1,
        entry_price=1.1,
        sl_distance=0.05,
        tp_distance=0.15,
        risk_usd=10.0,
        equity=10000.0,
        current_heat_usd=0.0,
        embargo_registry={}
    )
    verdict = peg.run_all_gates(ctx, ticket_ref="T1")
    assert not verdict.approved
    assert "Gate GATE-0-GLOBAL-CAP Failed" in verdict.summary()

# New tests for extracted gates

def test_gate1_ecn_conflict(mock_cfg):
    # Pass
    ctx = GateContext(
        symbol="EURUSD", direction="BUY", asset_class="FOREX", regime="BULL",
        kelly_lots=0.1, entry_price=1.1, sl_distance=0.05, tp_distance=0.15,
        risk_usd=10.0, equity=1000.0, current_heat_usd=0.0, embargo_registry={}
    )
    res = peg.gate1_ecn_conflict(ctx)
    assert res.status == ALLOW

    # Fail 1A: Equity
    ctx.equity = 50.0
    res = peg.gate1_ecn_conflict(ctx)
    assert res.status == BLOCK
    assert res.gate == "GATE-1A"

    # Fail 1B: Lots
    ctx.equity = 1000.0
    ctx.kelly_lots = 0.005
    res = peg.gate1_ecn_conflict(ctx)
    assert res.status == BLOCK
    assert res.gate == "GATE-1B"

def test_gate2_leverage_wall(mocked_mt5, mock_cfg):
    mocked_mt5.symbol_info.return_value = MagicMock(trade_contract_size=100000.0)

    # Pass
    ctx = GateContext(
        symbol="EURUSD", direction="BUY", asset_class="FOREX", regime="BULL",
        kelly_lots=0.1, entry_price=1.1, sl_distance=0.05, tp_distance=0.15,
        risk_usd=10.0, equity=10000.0, current_heat_usd=0.0, embargo_registry={}
    )
    res = peg.gate2_leverage_wall(ctx)
    assert res.status == ALLOW

    # Fail
    ctx.kelly_lots = 10.0
    ctx.equity = 1000.0
    res = peg.gate2_leverage_wall(ctx)
    assert res.status == BLOCK
    assert res.gate == "GATE-2"

def test_gate3_rr_ratio():
    # Pass BULL
    ctx = GateContext(
        symbol="EURUSD", direction="BUY", asset_class="FOREX", regime="BULL",
        kelly_lots=0.1, entry_price=1.1, sl_distance=0.01, tp_distance=0.02,
        risk_usd=10.0, equity=10000.0, current_heat_usd=0.0, embargo_registry={}
    )
    res = peg.gate3_rr_ratio(ctx)
    assert res.status == ALLOW

    # Fail BULL (RR < 2.0)
    ctx.tp_distance = 0.015
    res = peg.gate3_rr_ratio(ctx)
    assert res.status == BLOCK

    # Pass RANGE
    ctx.regime = "RANGE"
    res = peg.gate3_rr_ratio(ctx)
    assert res.status == ALLOW

def test_gate5_risk_cap_and_atr_floor(mocked_mt5, mock_cfg):
    # Pass
    mocked_mt5.copy_rates_from_pos.return_value = [
        (0, 1.1, 1.1001, 1.1, 1.1, 0, 0, 0) for _ in range(20)
    ]
    ctx = GateContext(
        symbol="EURUSD", direction="BUY", asset_class="FOREX", regime="BULL",
        kelly_lots=0.1, entry_price=1.1, sl_distance=0.05, tp_distance=0.15,
        risk_usd=10.0, equity=1000.0, current_heat_usd=0.0, embargo_registry={}
    )
    res = peg.gate5_risk_cap_and_atr_floor(ctx)
    assert res.status == ALLOW

    # Fail Risk Cap
    ctx.risk_usd = 50.0
    res = peg.gate5_risk_cap_and_atr_floor(ctx)
    assert res.status == BLOCK
    assert res.gate == "GATE-5-RISK-CAP"

    # Fail ATR Floor
    ctx.risk_usd = 10.0
    ctx.sl_distance = 0.01
    mocked_mt5.copy_rates_from_pos.return_value = [
        (0, 1.1, 1.2, 1.1, 1.1, 0, 0, 0) for _ in range(20)
    ]
    res = peg.gate5_risk_cap_and_atr_floor(ctx)
    assert res.status == BLOCK
    assert res.gate == "GATE-5-ATR-FLOOR"

def test_gate6_portfolio_heat(mock_cfg):
    # Pass
    ctx = GateContext(
        symbol="EURUSD", direction="BUY", asset_class="FOREX", regime="BULL",
        kelly_lots=0.1, entry_price=1.1, sl_distance=0.05, tp_distance=0.15,
        risk_usd=10.0, equity=10000.0, current_heat_usd=100.0, embargo_registry={}
    )
    res = peg.gate6_portfolio_heat(ctx)
    assert res.status == ALLOW

    # Fail
    ctx.risk_usd = 100.0
    ctx.current_heat_usd = 450.0
    res = peg.gate6_portfolio_heat(ctx)
    assert res.status == BLOCK
    assert res.gate == "GATE-6"

def test_gate7_weekend_blackout(mock_cfg):
    # Crypto passes regardless
    ctx = GateContext(
        symbol="BTCUSD", direction="BUY", asset_class="CRYPTO", regime="BULL",
        kelly_lots=0.1, entry_price=60000.0, sl_distance=1000.0, tp_distance=3000.0,
        risk_usd=10.0, equity=10000.0, current_heat_usd=0.0, embargo_registry={}
    )
    res = peg.gate7_weekend_blackout(ctx)
    assert res.status == ALLOW

    # Mock datetime to a weekend (Saturday)
    with patch("pre_execution_gate.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2025, 5, 24, 12, 0, 0, tzinfo=pytz.utc) # Saturday
        ctx.asset_class = "FOREX"
        res = peg.gate7_weekend_blackout(ctx)
        assert res.status == BLOCK
        assert "Weekend Blackout" in res.message

def test_gate8_amnesia_lock():
    # Pass
    ctx = GateContext(
        symbol="EURUSD", direction="BUY", asset_class="FOREX", regime="BULL",
        kelly_lots=0.1, entry_price=1.1, sl_distance=0.05, tp_distance=0.15,
        risk_usd=10.0, equity=10000.0, current_heat_usd=0.0, embargo_registry={}
    )
    res = peg.gate8_amnesia_lock(ctx)
    assert res.status == ALLOW

    # Fail
    ctx.embargo_registry = {"EURUSD": True}
    res = peg.gate8_amnesia_lock(ctx)
    assert res.status == BLOCK
    assert res.gate == "GATE-8"
