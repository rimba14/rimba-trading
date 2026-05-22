import pytest
import json
import os
import sys
from unittest.mock import patch, mock_open, MagicMock

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

from agents.hermes_diagnostics_mcp import get_pending_diagnostics, DIAGNOSTICS_DIR

def test_get_pending_diagnostics_success():
    """Test get_pending_diagnostics when a valid JSON file is present."""
    mock_files = ['test_diagnostic.json', 'not_json.txt']

    mock_data = {"issue": "test_issue", "status": "pending"}
    mock_file_content = json.dumps(mock_data)

    with patch('os.listdir', return_value=mock_files) as mock_listdir:
        with patch('builtins.open', mock_open(read_data=mock_file_content)) as m_open:
            # Execute
            result_json = get_pending_diagnostics()

            # Assertions
            result = json.loads(result_json)

            # Should only process the .json file
            assert len(result) == 1

            # Content should match, and _filename should be added
            assert result[0]['issue'] == 'test_issue'
            assert result[0]['_filename'] == 'test_diagnostic.json'

            # Check mocks were called with correct args
            mock_listdir.assert_called_once_with(DIAGNOSTICS_DIR)
            m_open.assert_called_once_with(os.path.join(DIAGNOSTICS_DIR, 'test_diagnostic.json'), 'r')

def test_get_pending_diagnostics_file_read_error():
    """Test get_pending_diagnostics handles file read errors gracefully."""
    mock_files = ['error_diagnostic.json']

    with patch('os.listdir', return_value=mock_files):
        # Mock open to raise an exception
        with patch('builtins.open', side_effect=Exception("Simulated read error")):
            with patch('agents.hermes_diagnostics_mcp.logging.error') as mock_log_error:
                # Execute
                result_json = get_pending_diagnostics()

                # Assertions
                result = json.loads(result_json)

                # Should be empty since it failed to read
                assert len(result) == 0
                assert result == []

                # Verify logging occurred
                mock_log_error.assert_called_once()
                assert "Failed to read diagnostic error_diagnostic.json" in mock_log_error.call_args[0][0]

def test_get_pending_diagnostics_json_parse_error():
    """Test get_pending_diagnostics handles invalid JSON gracefully."""
    mock_files = ['invalid_diagnostic.json']
    mock_file_content = "invalid json { content"

    with patch('os.listdir', return_value=mock_files):
        with patch('builtins.open', mock_open(read_data=mock_file_content)):
            with patch('agents.hermes_diagnostics_mcp.logging.error') as mock_log_error:
                # Execute
                result_json = get_pending_diagnostics()

                # Assertions
                result = json.loads(result_json)
                assert len(result) == 0

                mock_log_error.assert_called_once()
                assert "Failed to read diagnostic invalid_diagnostic.json" in mock_log_error.call_args[0][0]
