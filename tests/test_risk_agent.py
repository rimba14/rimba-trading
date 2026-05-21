import pytest
from unittest.mock import patch, MagicMock
from agents.risk_agent import calculate_currency_exposure

class MockPosition:
    def __init__(self, symbol, sl, price_open, volume, type_val):
        self.symbol = symbol
        self.sl = sl
        self.price_open = price_open
        self.volume = volume
        self.type = type_val

@patch("agents.risk_agent.mt5")
@patch("agents.risk_agent.get_usd_rate")
@patch("agents.risk_agent.parse_base_quote")
def test_calculate_currency_exposure_empty(mock_parse, mock_rate, mock_mt5):
    assert calculate_currency_exposure([]) == {}
    assert calculate_currency_exposure(None) == {}

@patch("agents.risk_agent.mt5")
@patch("agents.risk_agent.get_usd_rate")
@patch("agents.risk_agent.parse_base_quote")
def test_calculate_currency_exposure_buy_with_sl(mock_parse, mock_rate, mock_mt5):
    # Setup mocks
    mock_parse.return_value = ("EUR", "USD")
    mock_rate.return_value = 1.0 # USD is 1.0
    mock_sym_info = MagicMock()
    mock_sym_info.trade_contract_size = 100000.0
    mock_mt5.symbol_info.return_value = mock_sym_info

    # 1 lot EURUSD buy at 1.1000, sl at 1.0900 (100 pips risk)
    # risk_quote = abs(1.1000 - 1.0900) * 1.0 * 100000 = 0.01 * 100000 = 1000 USD
    pos = MockPosition("EURUSD", 1.0900, 1.1000, 1.0, 0)

    exposures = calculate_currency_exposure([pos])

    assert pytest.approx(exposures["EUR"]) == 1000.0
    assert pytest.approx(exposures["USD"]) == -1000.0

@patch("agents.risk_agent.mt5")
@patch("agents.risk_agent.get_usd_rate")
@patch("agents.risk_agent.parse_base_quote")
def test_calculate_currency_exposure_sell_without_sl(mock_parse, mock_rate, mock_mt5):
    # Setup mocks
    mock_parse.return_value = ("GBP", "JPY")
    mock_rate.return_value = 0.0067 # JPY to USD approx rate
    mock_sym_info = MagicMock()
    mock_sym_info.trade_contract_size = 100000.0
    mock_mt5.symbol_info.return_value = mock_sym_info

    # 2 lots GBPJPY sell at 150.00, no sl
    # fallback risk = volume * price_open * contract_size * 0.02
    # risk_quote = 2.0 * 150.00 * 100000.0 * 0.02 = 600,000 JPY
    # risk_usd = 600,000 * 0.0067 = 4020 USD
    pos = MockPosition("GBPJPY", 0.0, 150.00, 2.0, 1)

    exposures = calculate_currency_exposure([pos])

    assert pytest.approx(exposures["GBP"]) == -4020.0
    assert pytest.approx(exposures["JPY"]) == 4020.0

@patch("agents.risk_agent.mt5")
@patch("agents.risk_agent.get_usd_rate")
@patch("agents.risk_agent.parse_base_quote")
def test_calculate_currency_exposure_aggregation(mock_parse, mock_rate, mock_mt5):
    # Function returns based on the symbol
    def mock_parse_side_effect(symbol):
        if symbol == "EURUSD": return "EUR", "USD"
        if symbol == "GBPUSD": return "GBP", "USD"
        return symbol[:3], symbol[3:]
    mock_parse.side_effect = mock_parse_side_effect

    def mock_rate_side_effect(currency):
        return 1.0
    mock_rate.side_effect = mock_rate_side_effect

    mock_sym_info = MagicMock()
    mock_sym_info.trade_contract_size = 100000.0
    mock_mt5.symbol_info.return_value = mock_sym_info

    pos1 = MockPosition("EURUSD", 1.0900, 1.1000, 1.0, 0) # Buy EURUSD: EUR +1000, USD -1000
    pos2 = MockPosition("GBPUSD", 1.2600, 1.2500, 1.0, 1) # Sell GBPUSD: GBP -1000, USD +1000

    exposures = calculate_currency_exposure([pos1, pos2])

    assert pytest.approx(exposures["EUR"]) == 1000.0
    assert pytest.approx(exposures["GBP"]) == -1000.0
    assert pytest.approx(exposures["USD"]) == 0.0 # -1000 + 1000
