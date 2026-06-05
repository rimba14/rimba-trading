import pytest
from unittest.mock import MagicMock
from tp_placement_engine import TPPlacementEngine, AssetClass, TPValidationResult, StructuralLevel

@pytest.fixture
def mock_oracle():
    oracle = MagicMock()
    return oracle

@pytest.fixture
def engine(mock_oracle):
    return TPPlacementEngine(oracle_cache=mock_oracle)

def test_validate_tp_placement_crypto_veto(engine, mock_oracle):
    # Crypto Law 4
    mock_oracle.get_atr.return_value = 100.0
    result = engine.validate_tp_placement(
        symbol="BTCUSD",
        entry=60000.0,
        sl=59000.0,
        proposed_tp=62000.0,
        direction=1
    )
    assert result.is_valid is True
    assert result.asset_class == AssetClass.CRYPTO
    assert result.final_tp == 0.0

def test_validate_tp_placement_invalid_geometry_sl(engine):
    # SL distance <= 0
    result = engine.validate_tp_placement(
        symbol="EURUSD",
        entry=1.1000,
        sl=1.1000,
        proposed_tp=1.1100,
        direction=1
    )
    assert result.is_valid is False
    assert "SL distance is zero or negative" in result.rejection_reason

def test_validate_tp_placement_direction_mismatch_long(engine):
    # Long but TP <= entry
    result = engine.validate_tp_placement(
        symbol="EURUSD",
        entry=1.1000,
        sl=1.0900,
        proposed_tp=1.0950,
        direction=1
    )
    assert result.is_valid is False
    assert "Direction=LONG but proposed_tp" in result.rejection_reason

def test_validate_tp_placement_direction_mismatch_short(engine):
    # Short but TP >= entry
    result = engine.validate_tp_placement(
        symbol="EURUSD",
        entry=1.1000,
        sl=1.1100,
        proposed_tp=1.1050,
        direction=-1
    )
    assert result.is_valid is False
    assert "Direction=SHORT but proposed_tp" in result.rejection_reason

def test_validate_tp_placement_missing_atr(engine, mock_oracle):
    # Law 2 - ATR missing
    mock_oracle.get_atr.return_value = None
    result = engine.validate_tp_placement(
        symbol="EURUSD",
        entry=1.1000,
        sl=1.0900,
        proposed_tp=1.1200,
        direction=1
    )
    assert result.is_valid is False
    assert "D1 ATR(14) unavailable" in result.rejection_reason

def test_validate_tp_placement_atr_ceiling_binding(engine, mock_oracle):
    # Law 2 - ATR ceiling
    # ATR = 0.0100. 3 * ATR = 0.0300. Ceiling = 1.1000 + 0.0300 = 1.1300
    # Asset cap for FOREX_MAJOR is 4% = 0.0440. Ceiling = 1.1440
    # ATR ceiling should be binding (1.1300)
    mock_oracle.get_atr.return_value = 0.0100

    # We need to mock level_resolver or disable it to see ceiling application
    result = engine.validate_tp_placement(
        symbol="EURUSD",
        entry=1.1000,
        sl=1.0900,
        proposed_tp=1.1500,
        direction=1,
        use_structural_resolver=False
    )
    assert result.is_valid is True
    assert result.final_tp == pytest.approx(1.1300)
    assert result.adjusted is True
    assert result.binding_ceiling_label == "ATR"

def test_validate_tp_placement_asset_cap_binding(engine, mock_oracle):
    # Law 3 - Asset class cap
    # ATR = 0.0500. 3 * ATR = 0.1500. Ceiling = 1.1000 + 0.1500 = 1.2500
    # Asset cap for FOREX_MAJOR is 4% = 0.0440. Ceiling = 1.1440
    # Asset cap should be binding
    mock_oracle.get_atr.return_value = 0.0500

    result = engine.validate_tp_placement(
        symbol="EURUSD",
        entry=1.1000,
        sl=1.0900,
        proposed_tp=1.2000,
        direction=1,
        use_structural_resolver=False
    )
    assert result.is_valid is True
    assert result.final_tp == pytest.approx(1.1440)
    assert result.binding_ceiling_label == "AssetCap"

def test_validate_tp_placement_min_rr_gate_fails(engine, mock_oracle):
    # Law 5 - Min RR = 1.5
    # Entry 1.1000, SL 1.0900 (Dist 0.0100). Min TP = 1.1150
    # ATR = 0.0010. 3 * ATR = 0.0030. Ceiling = 1.1030
    # RR = 0.0030 / 0.0100 = 0.3 < 1.5. REJECT.
    mock_oracle.get_atr.return_value = 0.0010

    result = engine.validate_tp_placement(
        symbol="EURUSD",
        entry=1.1000,
        sl=1.0900,
        proposed_tp=1.1500,
        direction=1,
        use_structural_resolver=False
    )
    assert result.is_valid is False
    assert "R:R of 0.30 is below the minimum threshold" in result.rejection_reason

def test_validate_tp_placement_structural_level(engine, mock_oracle):
    # Law 1 - Structural level
    mock_oracle.get_atr.return_value = 0.0100 # Ceiling 1.1300

    # Mock level resolver
    mock_resolver = MagicMock()
    engine.level_resolver = mock_resolver

    level = StructuralLevel(
        price=1.1200,
        level_type="swing_high",
        source_tf="D1",
        strength=0.8,
        distance=0.0200,
        distance_pct=0.0181
    )
    mock_resolver.get_levels.return_value = [level]

    result = engine.validate_tp_placement(
        symbol="EURUSD",
        entry=1.1000,
        sl=1.0900,
        proposed_tp=1.1500,
        direction=1,
        use_structural_resolver=True
    )
    assert result.is_valid is True
    assert result.final_tp == 1.1200
    assert result.structural_level == level

def test_audit_open_position(engine, mock_oracle):
    mock_oracle.get_atr.return_value = 0.0100
    # Audit calls validate_tp_placement with use_structural_resolver=False
    result = engine.audit_open_position(
        symbol="EURUSD",
        entry=1.1000,
        sl=1.0900,
        current_tp=1.1500,
        direction=1
    )
    assert result.is_valid is True
    assert result.final_tp == pytest.approx(1.1300) # Capped at ATR ceiling
