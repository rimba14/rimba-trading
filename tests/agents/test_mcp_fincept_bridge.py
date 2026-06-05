import sys
import os
from unittest.mock import MagicMock, patch, mock_open
import json

# Mock FastMCP before importing the bridge
sys.modules['mcp.server.fastmcp'] = MagicMock()
fast_mcp_mock = MagicMock()
def mock_tool(*args, **kwargs):
    def decorator(func):
        return func
    return decorator
fast_mcp_mock.FastMCP.return_value.tool = mock_tool
sys.modules['mcp.server.fastmcp'].FastMCP = fast_mcp_mock.FastMCP

# Add root directory to path to allow importing from agents/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from agents.mcp_fincept_bridge import mcp_query_macro_sentiment, mcp_trigger_macro_halt

def test_mcp_query_macro_sentiment_success():
    query = "test query"
    result_json = mcp_query_macro_sentiment(query)
    result = json.loads(result_json)

    assert result["query"] == query
    assert result["status"] == "CONNECTED"
    assert "sentiment_score" in result
    assert "critical_events" in result
    assert "geopolitical_risk" in result
    assert "raw_payload_sample" in result

def test_mcp_trigger_macro_halt_success():
    reason = "Test Reason"
    m_open = mock_open()
    with patch("builtins.open", m_open):
        result = mcp_trigger_macro_halt(reason)

        assert "SUCCESS" in result
        assert reason in result

        # Verify file write
        m_open.assert_called_once_with("C:/Sentinel_Project/halt_signal.json", "w")
        handle = m_open()

        # Capture all calls to write
        written_data = "".join(call.args[0] for call in handle.write.call_args_list)
        payload = json.loads(written_data)

        assert payload["halt_active"] is True
        assert payload["reason"] == reason
        assert payload["source"] == "Fincept Macro Intelligence / Hermes Orchestrator"
        assert "timestamp_utc" in payload

def test_mcp_trigger_macro_halt_failure():
    reason = "Test Reason"
    with patch("builtins.open", side_effect=IOError("Permission Denied")):
        result = mcp_trigger_macro_halt(reason)
        assert result.startswith("FAILURE: Could not inject halt signal:")
        assert "Permission Denied" in result
