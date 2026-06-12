import pytest
from unittest.mock import MagicMock, patch
import sys
import json

# Define a mock decorator that returns the function as-is
def mock_tool_decorator(*args, **kwargs):
    def decorator(func):
        return func
    return decorator

# Mock dependencies before importing the module
mock_mcp_pkg = MagicMock()
mock_fastmcp = MagicMock()
mock_fastmcp.return_value.tool.side_effect = mock_tool_decorator

sys.modules['mcp'] = mock_mcp_pkg
sys.modules['mcp.server'] = mock_mcp_pkg.server
sys.modules['mcp.server.fastmcp'] = mock_mcp_pkg.server.fastmcp
mock_mcp_pkg.server.fastmcp.FastMCP = mock_fastmcp

sys.modules['yfinance'] = MagicMock()

import agents.alt_data_oracle_mcp as oracle

def test_fetch_unstructured_sentiment_happy_path():
    mock_ticker = MagicMock()
    mock_ticker.news = [
        {"title": "Test News 1", "publisher": "Test Pub 1", "link": "http://test1.com", "providerPublishTime": 12345, "type": "STORY"},
        {"title": "Test News 2", "publisher": "Test Pub 2", "link": "http://test2.com", "providerPublishTime": 67890}
    ]

    with patch('agents.alt_data_oracle_mcp.yf.Ticker', return_value=mock_ticker):
        with patch('time.time', return_value=1000000):
            result_json = oracle.fetch_unstructured_sentiment("AAPL", "Equity")
            result = json.loads(result_json)

            assert result["symbol"] == "AAPL"
            assert result["asset_class"] == "Equity"
            assert result["count"] == 2
            assert len(result["headlines"]) == 2
            assert result["headlines"][0]["title"] == "Test News 1"
            assert result["headlines"][1]["type"] == "STORY" # Default value from code
            assert result["timestamp_utc"] == 1000000

def test_fetch_unstructured_sentiment_no_news():
    mock_ticker = MagicMock()
    mock_ticker.news = []

    with patch('agents.alt_data_oracle_mcp.yf.Ticker', return_value=mock_ticker):
        result_json = oracle.fetch_unstructured_sentiment("EMPTY", "Crypto")
        result = json.loads(result_json)

        assert result["status"] == "NO_DATA"
        assert "No recent headlines found" in result["message"]
        assert result["headlines"] == []

def test_fetch_unstructured_sentiment_error():
    with patch('agents.alt_data_oracle_mcp.yf.Ticker', side_effect=Exception("API Error")):
        result_json = oracle.fetch_unstructured_sentiment("ERROR", "Forex")
        result = json.loads(result_json)

        assert result["status"] == "ERROR"
        assert "Sentiment Fetch Failed: API Error" in result["message"]

def test_fetch_unstructured_sentiment_limit_25():
    mock_ticker = MagicMock()
    mock_ticker.news = [{"title": f"News {i}"} for i in range(30)]

    with patch('agents.alt_data_oracle_mcp.yf.Ticker', return_value=mock_ticker):
        result_json = oracle.fetch_unstructured_sentiment("MANY", "Equity")
        result = json.loads(result_json)

        assert result["count"] == 25
        assert len(result["headlines"]) == 25
