import os
import json
import logging
from unittest.mock import patch, mock_open, MagicMock
import sys
import importlib.util

import pytest

# Create a mock for mcp.server.fastmcp.FastMCP that doesn't mess up the decorated functions
mock_mcp_module = MagicMock()
class MockFastMCP:
    def __init__(self, *args, **kwargs):
        pass
    def tool(self, *args, **kwargs):
        def decorator(func):
            # Just return the function unchanged
            return func
        return decorator
    def run(self):
        pass

mock_mcp_module.FastMCP = MockFastMCP
sys.modules['mcp.server.fastmcp'] = mock_mcp_module

spec = importlib.util.spec_from_file_location("hermes_diagnostics_mcp", "agents/hermes_diagnostics_mcp.py")
hermes_diagnostics_mcp = importlib.util.module_from_spec(spec)
sys.modules["agents.hermes_diagnostics_mcp"] = hermes_diagnostics_mcp
spec.loader.exec_module(hermes_diagnostics_mcp)

from agents.hermes_diagnostics_mcp import get_pending_diagnostics, apply_sre_patch

@patch('agents.hermes_diagnostics_mcp.os.listdir')
def test_get_pending_diagnostics_success(mock_listdir):
    # Mocking listdir to return .json and non-.json files
    mock_listdir.return_value = ['test1.json', 'test2.json', 'ignore.txt']

    def mock_open_side_effect(filename, *args, **kwargs):
        if 'test1.json' in filename:
            return mock_open(read_data='{"id": 1}')()
        if 'test2.json' in filename:
            return mock_open(read_data='{"id": 2}')()
        raise FileNotFoundError(f"File {filename} not found in mock")

    with patch('builtins.open', side_effect=mock_open_side_effect):
        result = get_pending_diagnostics()

        # Check result
        expected_diagnostics = [
            {"id": 1, "_filename": "test1.json"},
            {"id": 2, "_filename": "test2.json"}
        ]

        # Check that it returns correct json structure
        parsed_result = json.loads(result)
        assert len(parsed_result) == 2
        assert parsed_result == expected_diagnostics

@patch('agents.hermes_diagnostics_mcp.logging.error')
@patch('agents.hermes_diagnostics_mcp.os.listdir')
def test_get_pending_diagnostics_error(mock_listdir, mock_logging_error):
    # Mocking listdir to return two json files
    mock_listdir.return_value = ['good.json', 'bad.json']

    # Mocking file content, 'bad.json' will raise JSONDecodeError
    def mock_open_side_effect(filename, *args, **kwargs):
        if 'good.json' in filename:
            return mock_open(read_data='{"status": "ok"}')()
        elif 'bad.json' in filename:
            return mock_open(read_data='invalid json')()
        raise FileNotFoundError(f"File {filename} not found in mock")

    with patch('builtins.open', side_effect=mock_open_side_effect):
        result = get_pending_diagnostics()

        # Check result: should only contain data from 'good.json'
        expected_diagnostics = [
            {"status": "ok", "_filename": "good.json"}
        ]

        parsed_result = json.loads(result)
        assert len(parsed_result) == 1
        assert parsed_result == expected_diagnostics

        # Verify that logging.error was called for 'bad.json'
        mock_logging_error.assert_called_once()
        args, kwargs = mock_logging_error.call_args
        assert "Failed to read diagnostic bad.json" in args[0]


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
