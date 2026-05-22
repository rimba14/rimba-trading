import pytest
from unittest.mock import patch, mock_open
from agents.sre_watchdog_mcp import patch_codebase

def test_patch_codebase_file_not_found():
    with patch("os.path.exists", return_value=False):
        result = patch_codebase("nonexistent_file.py", "old", "new")
        assert "Error: File nonexistent_file.py not found." in result

def test_patch_codebase_exact_match_not_found():
    with patch("os.path.exists", return_value=True):
        with patch("shutil.copy2"):
            # Mock open so that reading returns content without old_code_block
            with patch("builtins.open", mock_open(read_data="some other code")):
                result = patch_codebase("existing_file.py", "old", "new")
                assert "Error: Exact code block to replace not found in target file." in result

def test_patch_codebase_successful():
    with patch("os.path.exists", return_value=True):
        with patch("shutil.copy2") as mock_copy:
            m_open = mock_open(read_data="def foo():\n    return 'old'\n")
            with patch("builtins.open", m_open):
                with patch("agents.sre_watchdog_mcp.notifier.send_intervention_alert") as mock_alert:
                    result = patch_codebase("existing_file.py", "return 'old'", "return 'new'")

                    assert "Patch Applied successfully" in result
                    mock_copy.assert_called_once_with("existing_file.py", "existing_file.py.bak")
                    mock_alert.assert_called_once()

                    # Verify write was called with new content
                    handle = m_open()
                    handle.write.assert_called_with("def foo():\n    return 'new'\n")

def test_patch_codebase_exception_handling():
    with patch("os.path.exists", return_value=True):
        with patch("shutil.copy2", side_effect=Exception("Permission denied")):
            result = patch_codebase("existing_file.py", "old", "new")
            assert "Error during patching: Permission denied" in result
