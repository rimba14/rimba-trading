import os
import json
import logging
from unittest.mock import patch, mock_open, MagicMock

import pytest

# Adjusting import path for tests
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from agents.hermes_diagnostics_mcp import get_pending_diagnostics

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
