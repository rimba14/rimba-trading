import sys
import os
from unittest.mock import MagicMock, patch, mock_open

# Mock FastMCP before importing the agent
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

from agents.hermes_diagnostics_mcp import (
    get_pending_diagnostics,
    resolve_diagnostic,
    apply_sre_patch,
    send_sre_webhook,
    DIAGNOSTICS_DIR,
    DISCORD_WEBHOOK
)

# --- get_pending_diagnostics Tests ---

def test_get_pending_diagnostics_success():
    """Test get_pending_diagnostics when a valid JSON file is present."""
    mock_files = ['test_diagnostic.json', 'not_json.txt']
    mock_data = {"issue": "test_issue", "status": "pending"}
    mock_file_content = json.dumps(mock_data)

    with patch('os.listdir', return_value=mock_files) as mock_listdir:
        with patch('builtins.open', mock_open(read_data=mock_file_content)) as m_open:
            result_json = get_pending_diagnostics()
            result = json.loads(result_json)

            assert len(result) == 1
            assert result[0]['issue'] == 'test_issue'
            assert result[0]['_filename'] == 'test_diagnostic.json'
            mock_listdir.assert_called_once_with(DIAGNOSTICS_DIR)

def test_get_pending_diagnostics_file_read_error():
    """Test get_pending_diagnostics handles file read errors gracefully."""
    mock_files = ['error_diagnostic.json']
    with patch('os.listdir', return_value=mock_files):
        with patch('builtins.open', side_effect=Exception("Simulated read error")):
            with patch('agents.hermes_diagnostics_mcp.logging.error') as mock_log_error:
                result_json = get_pending_diagnostics()
                result = json.loads(result_json)
                assert len(result) == 0
                mock_log_error.assert_called_once()
                assert "Failed to read diagnostic error_diagnostic.json" in mock_log_error.call_args[0][0]

# --- resolve_diagnostic Tests ---

def test_resolve_diagnostic_success():
    """Test resolve_diagnostic when the file exists and is deleted."""
    filename = "test_diagnostic.json"
    with patch('os.path.exists', return_value=True):
        with patch('os.remove') as mock_remove:
            result_json = resolve_diagnostic(filename)
            result = json.loads(result_json)
            assert result['status'] == 'success'
            mock_remove.assert_called_once_with(os.path.join(DIAGNOSTICS_DIR, filename))

def test_resolve_diagnostic_not_found():
    """Test resolve_diagnostic when the file does not exist."""
    filename = "missing_diagnostic.json"
    with patch('os.path.exists', return_value=False):
        result_json = resolve_diagnostic(filename)
        result = json.loads(result_json)
        assert result['status'] == 'error'
        assert result['message'] == 'FILE_NOT_FOUND'

# --- apply_sre_patch Tests ---

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
        m_open.return_value.write.assert_called_once_with("def foo():\n    return 43\n")
        mock_webhook.assert_called_once_with("file.txt", "CODE_PATCH_APPLIED", "Patched pattern: return 42...")

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

# --- send_sre_webhook Tests ---

@patch("requests.post")
def test_send_sre_webhook_success(mock_post):
    with patch("agents.hermes_diagnostics_mcp.datetime") as mock_datetime:
        fixed_now = datetime.datetime(2023, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = fixed_now

        target = "file.txt"
        event = "TEST_EVENT"
        details = "Test Details"

        send_sre_webhook(target, event, details)

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args

        assert args[0] == DISCORD_WEBHOOK
        assert kwargs["timeout"] == 10

        payload = kwargs["json"]
        assert "embeds" in payload
        assert len(payload["embeds"]) == 1

        embed = payload["embeds"][0]
        assert embed["title"] == f"🛠️ SRE AUTO-RESOLUTION: {event}"
        assert embed["description"] == f"**Target:** `{target}`\n**Details:** {details}"
        assert embed["color"] == 0xFF5733
        assert embed["timestamp"] == fixed_now.isoformat()

@patch("requests.post", side_effect=Exception("Connection Error"))
def test_send_sre_webhook_handles_exception(mock_post):
    """Ensure send_sre_webhook does not crash if the request fails."""
    # This should not raise
    send_sre_webhook("file.txt", "EVENT", "Details")
    mock_post.assert_called_once()

def test_send_sre_webhook_no_requests():
    """Test send_sre_webhook when requests module is missing or cannot be imported."""
    # We use patch.dict to mock sys.modules to simulate missing 'requests'
    with patch.dict(sys.modules, {'requests': None}):
        # This should not raise ImportError because it's caught inside the function
        send_sre_webhook("file.txt", "EVENT", "Details")
