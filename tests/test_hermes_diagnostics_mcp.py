import os
import json
from unittest.mock import patch

from agents.hermes_diagnostics_mcp import resolve_diagnostic, DIAGNOSTICS_DIR

@patch('os.path.exists')
@patch('os.remove')
def test_resolve_diagnostic_success(mock_remove, mock_exists):
    mock_exists.return_value = True
    result = json.loads(resolve_diagnostic("test.json"))
    assert result == {"status": "success", "message": "Resolved test.json"}
    mock_exists.assert_called_once_with(os.path.join(DIAGNOSTICS_DIR, "test.json"))
    mock_remove.assert_called_once_with(os.path.join(DIAGNOSTICS_DIR, "test.json"))

@patch('os.path.exists')
@patch('os.remove')
def test_resolve_diagnostic_not_found(mock_remove, mock_exists):
    mock_exists.return_value = False
    result = json.loads(resolve_diagnostic("missing.json"))
    assert result == {"status": "error", "message": "FILE_NOT_FOUND"}
    mock_exists.assert_called_once_with(os.path.join(DIAGNOSTICS_DIR, "missing.json"))
    mock_remove.assert_not_called()
