import pytest
import json
import os
import sys
import datetime
from unittest.mock import patch, mock_open, MagicMock

# Mock FastMCP before importing the agent
mock_mcp_module = MagicMock()
class MockFastMCP:
    def __init__(self, *args, **kwargs):
        pass
    def tool(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator
    def run(self):
        pass

mock_mcp_module.FastMCP = MockFastMCP
sys.modules['mcp.server.fastmcp'] = mock_mcp_module

# Add root directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from agents.hermes_diagnostics_mcp import (
    get_pending_diagnostics,
    resolve_diagnostic,
    apply_sre_patch,
    send_sre_webhook,
    DIAGNOSTICS_DIR
)

# --- Tests for get_pending_diagnostics ---

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

def test_get_pending_diagnostics_json_parse_error():
    """Test get_pending_diagnostics handles invalid JSON gracefully."""
    mock_files = ['invalid_diagnostic.json']
    mock_file_content = "invalid json { content"

    with patch('os.listdir', return_value=mock_files):
        with patch('builtins.open', mock_open(read_data=mock_file_content)):
            with patch('agents.hermes_diagnostics_mcp.logging.error') as mock_log_error:
                result_json = get_pending_diagnostics()
                result = json.loads(result_json)
                assert len(result) == 0
                mock_log_error.assert_called_once()
                assert "Failed to read diagnostic invalid_diagnostic.json" in mock_log_error.call_args[0][0]

def test_get_pending_diagnostics_json_load_error_continues_loop():
    """Test that get_pending_diagnostics continues loop if json.load fails for one file."""
    mock_files = ['invalid.json', 'valid.json']

    def mock_open_side_effect(path, mode):
        if 'invalid.json' in path:
            return mock_open(read_data='{invalid: json}')()
        else:
            return mock_open(read_data='{"status": "ok"}')()

    with patch('os.listdir', return_value=mock_files):
        with patch('builtins.open', side_effect=mock_open_side_effect):
            # We mock json.load specifically to raise error for invalid.json
            original_json_load = json.load
            def json_load_side_effect(fp):
                content = fp.read()
                if 'invalid' in content:
                    raise json.JSONDecodeError("Expecting property name enclosed in double quotes", content, 1)
                return json.loads(content)

            with patch('json.load', side_effect=json_load_side_effect):
                with patch('agents.hermes_diagnostics_mcp.logging.error') as mock_log_error:
                    result_json = get_pending_diagnostics()
                    result = json.loads(result_json)

                    # Should have processed valid.json even though invalid.json failed
                    assert len(result) == 1
                    assert result[0]['status'] == 'ok'
                    assert result[0]['_filename'] == 'valid.json'

                    # Verify logging occurred for the failed file
                    mock_log_error.assert_called_once()
                    assert "Failed to read diagnostic invalid.json" in mock_log_error.call_args[0][0]

# --- Tests for resolve_diagnostic ---

def test_resolve_diagnostic_success():
    with patch('os.path.exists', return_value=True), \
         patch('os.remove') as mock_remove:
        result_json = resolve_diagnostic("test.json")
        result = json.loads(result_json)
        assert result["status"] == "success"
        mock_remove.assert_called_once()

def test_resolve_diagnostic_not_found():
    with patch('os.path.exists', return_value=False):
        result_json = resolve_diagnostic("missing.json")
        result = json.loads(result_json)
        assert result["status"] == "error"
        assert result["message"] == "FILE_NOT_FOUND"

# --- Tests for apply_sre_patch ---

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
        m_open.return_value.write.assert_called_once_with("def foo():\n    return 43\n")
        mock_webhook.assert_called_once()

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

# --- Tests for send_sre_webhook ---

@patch("requests.post")
def test_send_sre_webhook_success(mock_post):
    with patch("agents.hermes_diagnostics_mcp.datetime") as mock_datetime:
        mock_datetime.utcnow.return_value = datetime.datetime(2023, 1, 1, 12, 0, 0)
        send_sre_webhook("file.txt", "TEST_EVENT", "Test Details")
        mock_post.assert_called_once()

@patch("requests.post", side_effect=Exception("Mocked Request Error"))
def test_send_sre_webhook_exception(mock_post):
    # Should not raise an exception
    send_sre_webhook("file.txt", "TEST_EVENT", "Test Details")
    mock_post.assert_called_once()
