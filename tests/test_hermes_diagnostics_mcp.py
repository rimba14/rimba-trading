import pytest
import json
from unittest.mock import patch, mock_open

from agents.hermes_diagnostics_mcp import apply_sre_patch

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
