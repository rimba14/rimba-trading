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

from agents.hermes_diagnostics_mcp import (
    apply_sre_patch,
    send_sre_webhook,
    get_pending_diagnostics,
    resolve_diagnostic,
    DIAGNOSTICS_DIR
)

def test_get_pending_diagnostics_success():
    """Test get_pending_diagnostics when valid JSON files are present."""
    mock_files = ['diag1.json', 'diag2.json']
    mock_data1 = {"id": 1, "msg": "test1"}
    mock_data2 = {"id": 2, "msg": "test2"}

    def side_effect(path, mode='r'):
        if 'diag1.json' in path:
            return mock_open(read_data=json.dumps(mock_data1))()
        elif 'diag2.json' in path:
            return mock_open(read_data=json.dumps(mock_data2))()
        return mock_open()()

    with patch('os.listdir', return_value=mock_files) as mock_listdir:
        with patch('builtins.open', side_effect=side_effect):
            result_json = get_pending_diagnostics()
            result = json.loads(result_json)

            assert len(result) == 2
            assert result[0]['id'] == 1
            assert result[0]['_filename'] == 'diag1.json'
            assert result[1]['id'] == 2
            assert result[1]['_filename'] == 'diag2.json'
            mock_listdir.assert_called_once_with(DIAGNOSTICS_DIR)

def test_get_pending_diagnostics_empty():
    """Test get_pending_diagnostics when the directory is empty."""
    with patch('os.listdir', return_value=[]):
        result_json = get_pending_diagnostics()
        result = json.loads(result_json)
        assert result == []

def test_get_pending_diagnostics_filtering():
    """Test get_pending_diagnostics filters out non-JSON files."""
    mock_files = ['diag1.json', 'image.png', 'README.md']
    mock_data = {"id": 1}

    with patch('os.listdir', return_value=mock_files):
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_data))):
            result_json = get_pending_diagnostics()
            result = json.loads(result_json)
            assert len(result) == 1
            assert result[0]['_filename'] == 'diag1.json'

def test_get_pending_diagnostics_read_error():
    """Test get_pending_diagnostics handles file read errors gracefully."""
    mock_files = ['error.json']
    with patch('os.listdir', return_value=mock_files):
        with patch('builtins.open', side_effect=IOError("Simulated IO Error")):
            with patch('agents.hermes_diagnostics_mcp.logging.error') as mock_log:
                result_json = get_pending_diagnostics()
                result = json.loads(result_json)
                assert result == []
                mock_log.assert_called_once()
                assert "Failed to read diagnostic error.json" in mock_log.call_args[0][0]

def test_get_pending_diagnostics_json_error():
    """Test get_pending_diagnostics handles invalid JSON gracefully."""
    mock_files = ['invalid.json']
    with patch('os.listdir', return_value=mock_files):
        with patch('builtins.open', mock_open(read_data="not a json")):
            with patch('agents.hermes_diagnostics_mcp.logging.error') as mock_log:
                result_json = get_pending_diagnostics()
                result = json.loads(result_json)
                assert result == []
                mock_log.assert_called_once()
                assert "Failed to read diagnostic invalid.json" in mock_log.call_args[0][0]

def test_resolve_diagnostic_success():
    """Test resolve_diagnostic when the file exists."""
    filename = "diag1.json"
    with patch('os.path.exists', return_value=True) as mock_exists:
        with patch('os.remove') as mock_remove:
            result_json = resolve_diagnostic(filename)
            result = json.loads(result_json)
            assert result['status'] == 'success'
            mock_remove.assert_called_once_with(os.path.join(DIAGNOSTICS_DIR, filename))

def test_resolve_diagnostic_not_found():
    """Test resolve_diagnostic when the file does not exist."""
    filename = "missing.json"
    with patch('os.path.exists', return_value=False):
        result_json = resolve_diagnostic(filename)
        result = json.loads(result_json)
        assert result['status'] == 'error'
        assert result['message'] == 'FILE_NOT_FOUND'

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
