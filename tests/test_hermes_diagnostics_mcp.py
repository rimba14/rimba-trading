import sys
import os
from unittest.mock import MagicMock, patch, mock_open

# Mock FastMCP
sys.modules['mcp.server.fastmcp'] = MagicMock()
fast_mcp_mock = MagicMock()
def mock_tool(*args, **kwargs):
    def decorator(func):
        return func
    return decorator
fast_mcp_mock.FastMCP.return_value.tool = mock_tool
sys.modules['mcp.server.fastmcp'].FastMCP = fast_mcp_mock.FastMCP

# Add root directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import json
import datetime

from agents.hermes_diagnostics_mcp import apply_sre_patch, send_sre_webhook

def test_apply_sre_patch_permission_denied():
    with patch("agents.hermes_diagnostics_mcp.os.path.abspath") as mock_abspath:
        mock_abspath.return_value = "/outside/path/file.txt"

        result_json = apply_sre_patch("file.txt", "search", "replace")
        result = json.loads(result_json)

        assert result["status"] == "error"
        assert "PERMISSION_DENIED" in result["message"]

def test_apply_sre_patch_file_not_found():
    with patch("agents.hermes_diagnostics_mcp.os.path.abspath") as mock_abspath, \
         patch("agents.hermes_diagnostics_mcp.os.path.exists") as mock_exists:

        mock_abspath.return_value = "C:\\Sentinel_Project\\file.txt"
        mock_exists.return_value = False

        result_json = apply_sre_patch("file.txt", "search", "replace")
        result = json.loads(result_json)

        assert result["status"] == "error"
        assert "FILE_NOT_FOUND" in result["message"]

def test_apply_sre_patch_pattern_not_found():
    with patch("agents.hermes_diagnostics_mcp.os.path.abspath") as mock_abspath, \
         patch("agents.hermes_diagnostics_mcp.os.path.exists") as mock_exists, \
         patch("builtins.open", mock_open(read_data="some content here")):

        mock_abspath.return_value = "C:\\Sentinel_Project\\file.txt"
        mock_exists.return_value = True

        result_json = apply_sre_patch("file.txt", "missing_pattern", "replace")
        result = json.loads(result_json)

        assert result["status"] == "error"
        assert result["message"] == "PATTERN_NOT_FOUND"

def test_apply_sre_patch_success():
    m_open = mock_open(read_data="def foo():\n    return 42\n")
    with patch("agents.hermes_diagnostics_mcp.os.path.abspath") as mock_abspath, \
         patch("agents.hermes_diagnostics_mcp.os.path.exists") as mock_exists, \
         patch("builtins.open", m_open), \
         patch("agents.hermes_diagnostics_mcp.send_sre_webhook") as mock_webhook:

        mock_abspath.return_value = "C:\\Sentinel_Project\\file.txt"
        mock_exists.return_value = True

        result_json = apply_sre_patch("file.txt", "return 42", "return 43")
        result = json.loads(result_json)

        assert result["status"] == "success"
        assert "PATCH_APPLIED" in result["message"]

        m_open.return_value.write.assert_called_once_with("def foo():\n    return 43\n")
        mock_webhook.assert_called_once_with("file.txt", "CODE_PATCH_APPLIED", "Patched pattern: return 42...")

def test_apply_sre_patch_exception():
    with patch("agents.hermes_diagnostics_mcp.os.path.abspath") as mock_abspath, \
         patch("agents.hermes_diagnostics_mcp.os.path.exists") as mock_exists, \
         patch("builtins.open", side_effect=PermissionError("Mocked Permission Error")):

        mock_abspath.return_value = "C:\\Sentinel_Project\\file.txt"
        mock_exists.return_value = True

        result_json = apply_sre_patch("file.txt", "search", "replace")
        result = json.loads(result_json)

        assert result["status"] == "error"
        assert "Mocked Permission Error" in result["message"]

@patch("requests.post")
def test_send_sre_webhook_success(mock_post):
    with patch("agents.hermes_diagnostics_mcp.datetime") as mock_datetime:
        mock_datetime.utcnow.return_value = datetime.datetime(2023, 1, 1, 12, 0, 0)

        send_sre_webhook("file.txt", "TEST_EVENT", "Test Details")

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args

        assert kwargs["timeout"] == 10
        assert "json" in kwargs

        payload = kwargs["json"]
        assert "embeds" in payload
        assert len(payload["embeds"]) == 1

        embed = payload["embeds"][0]
        assert embed["title"] == "🛠️ SRE AUTO-RESOLUTION: TEST_EVENT"
        assert embed["description"] == "**Target:** `file.txt`\n**Details:** Test Details"
        assert embed["color"] == 0xFF5733

@patch("requests.post", side_effect=Exception("Mocked Request Error"))
def test_send_sre_webhook_exception(mock_post):
    # Should not raise an exception
    send_sre_webhook("file.txt", "TEST_EVENT", "Test Details")
    mock_post.assert_called_once()
