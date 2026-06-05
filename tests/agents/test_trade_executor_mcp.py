import pytest
from unittest.mock import MagicMock, patch
import sys

# Mock dependencies before importing the module
sys.modules['MetaTrader5'] = MagicMock()
sys.modules['gitagent_utils'] = MagicMock()
# Mock mcp to avoid issues with FastMCP
sys.modules['mcp'] = MagicMock()
sys.modules['mcp.server'] = MagicMock()
sys.modules['mcp.server.fastmcp'] = MagicMock()

import agents.trade_executor_mcp as te

def test_calculate_kelly_lot_size_happy_path():
    # p = 0.6, equity = 10000, sl_points = 100, tick_value = 10, tick_size = 0.01, point = 0.01
    # p_val = 0.6, q_val = 0.4, b = 1.5
    # f_star = 0.6 - (0.4 / 1.5) = 0.6 - 0.2666... = 0.3333...
    # f_star *= 0.25 (default KELLY_FRACTION) = 0.08333...
    # f_star = min(0.08333..., 0.02) = 0.02
    # risk_dollars = 10000 * 0.02 = 200
    # point_val = 10 / (0.01 / 0.01) = 10
    # lots = 200 / ((100 / 0.01) * 10 + 1e-12) = 200 / (10000 * 10) = 200 / 100000 = 0.002

    # Wait, let's re-calculate point_val and lots carefully.
    # point_val = tick_value / (tick_size / point)
    # If tick_size == point, then point_val = tick_value.
    # lots = risk_dollars / ((sl_points / point) * point_val + 1e-12)
    # If sl_points is 100 and point is 0.01, sl_points/point = 10000.
    # lots = 200 / (10000 * 10) = 0.002.

    with patch('agents.trade_executor_mcp.get_dynamic_risk_params') as mock_get_params:
        mock_get_params.return_value = {
            "epistemic_gate": 0.82,
            "kelly_fraction": 0.25,
            "virtual_sl_multiplier": None
        }

        lots = te.calculate_kelly_lot_size(
            p=0.6,
            equity=10000.0,
            sl_points=0.01, # Using small sl_points to avoid tiny lots
            tick_value=1.0,
            tick_size=0.00001,
            point=0.00001
        )
        # p_val = 0.6, q_val = 0.4, b = 1.5
        # f_star = 0.6 - (0.4/1.5) = 0.333...
        # f_star *= 0.25 = 0.0833...
        # f_star = min(0.0833, 0.02) = 0.02
        # risk_dollars = 10000 * 0.02 = 200
        # point_val = 1.0 / (0.00001 / 0.00001) = 1.0
        # lots = 200 / ((0.01 / 0.00001) * 1.0) = 200 / 1000 = 0.2

        assert pytest.approx(lots) == 0.2

def test_calculate_kelly_lot_size_sl_zero():
    lots = te.calculate_kelly_lot_size(0.6, 10000.0, 0.0, 1.0, 0.00001, 0.00001)
    assert lots == 0.0

def test_calculate_kelly_lot_size_low_p():
    # p = 0.4. Should use 1.0 - 0.4 = 0.6
    with patch('agents.trade_executor_mcp.get_dynamic_risk_params') as mock_get_params:
        mock_get_params.return_value = {
            "epistemic_gate": 0.82,
            "kelly_fraction": 0.25,
            "virtual_sl_multiplier": None
        }

        lots = te.calculate_kelly_lot_size(
            p=0.4,
            equity=10000.0,
            sl_points=0.01,
            tick_value=1.0,
            tick_size=0.00001,
            point=0.00001
        )
        # Should be same as p=0.6
        assert pytest.approx(lots) == 0.2

def test_calculate_kelly_lot_size_max_risk_cap():
    # Force f_star to be very high to test capping
    with patch('agents.trade_executor_mcp.get_dynamic_risk_params') as mock_get_params:
        mock_get_params.return_value = {
            "epistemic_gate": 0.82,
            "kelly_fraction": 1.0, # Full Kelly
            "virtual_sl_multiplier": None
        }
        # p=0.9, q=0.1, b=1.5
        # f_star = 0.9 - (0.1/1.5) = 0.9 - 0.0666 = 0.8333
        # f_star *= 1.0 = 0.8333
        # f_star = min(0.8333, 0.02) = 0.02

        lots = te.calculate_kelly_lot_size(
            p=0.9,
            equity=10000.0,
            sl_points=0.01,
            tick_value=1.0,
            tick_size=0.00001,
            point=0.00001
        )
        assert pytest.approx(lots) == 0.2 # 10000 * 0.02 / 1000 = 0.2

def test_calculate_kelly_lot_size_custom_params():
    with patch('agents.trade_executor_mcp.get_dynamic_risk_params') as mock_get_params:
        mock_get_params.return_value = {
            "epistemic_gate": 0.82,
            "kelly_fraction": 0.1, # 1/10 Kelly
            "virtual_sl_multiplier": None
        }
        # p=0.7, q=0.3, b=1.5
        # f_star = 0.7 - (0.3/1.5) = 0.7 - 0.2 = 0.5
        # f_star *= 0.1 = 0.05
        # f_star = min(0.05, 0.02) = 0.02

        lots = te.calculate_kelly_lot_size(
            p=0.7,
            equity=10000.0,
            sl_points=0.01,
            tick_value=1.0,
            tick_size=0.00001,
            point=0.00001
        )
        assert pytest.approx(lots) == 0.2

def test_calculate_kelly_lot_size_math_variation():
    with patch('agents.trade_executor_mcp.get_dynamic_risk_params') as mock_get_params:
        mock_get_params.return_value = {
            "epistemic_gate": 0.82,
            "kelly_fraction": 0.25,
            "virtual_sl_multiplier": None
        }
        # p=0.8, q=0.2, b=1.5
        # f_star = 0.8 - (0.2/1.5) = 0.8 - 0.1333... = 0.6666...
        # f_star *= 0.25 = 0.1666...
        # f_star = min(0.1666..., 0.02) = 0.02

        # Change equity and sl_points
        # risk_dollars = 50000 * 0.02 = 1000
        # sl_points = 0.05, point = 0.0001
        # sl_points / point = 500
        # tick_value = 10.0, tick_size = 0.001
        # point_val = 10.0 / (0.001 / 0.0001) = 1.0
        # lots = 1000 / (500 * 1.0) = 2.0

        lots = te.calculate_kelly_lot_size(
            p=0.8,
            equity=50000.0,
            sl_points=0.05,
            tick_value=10.0,
            tick_size=0.001,
            point=0.0001
        )
        assert pytest.approx(lots) == 2.0
