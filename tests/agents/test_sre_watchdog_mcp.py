import pytest
from unittest.mock import patch, mock_open, MagicMock
from agents.sre_watchdog_mcp import patch_codebase, restart_service

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

def test_restart_service_safe_command_construction():
    with patch("subprocess.run") as mock_run:
        with patch("subprocess.Popen") as mock_popen:
            with patch("agents.sre_watchdog_mcp.notifier.send_intervention_alert"):
                # Use a service name that exists in the dictionary
                service_name = "slow_loop"
                result = restart_service(service_name)

                assert "Service slow_loop restart initiated." == result

                # Check how Popen was called
                args, kwargs = mock_popen.call_args

                # Ensure shell=False is used
                assert kwargs.get("shell") is False

                # Ensure it's a list
                cmd_list = args[0]
                assert isinstance(cmd_list, list)

                # Verify the command list contents
                assert "cmd.exe" == cmd_list[0]
                assert "/c" == cmd_list[1]
                assert "start" == cmd_list[2]
                assert f"SENTINEL RESTART: {service_name}" == cmd_list[3]
                assert "/D" == cmd_list[4]
                assert "C:\\Sentinel_Project" == cmd_list[5]
                assert "cmd" == cmd_list[6]
                assert "/k" == cmd_list[7]
                assert "call venv\\Scripts\\activate && python sentinel_slow_loop.py" == cmd_list[8]

                # Verify subprocess.run was called for wmic
                mock_run.assert_called_once()
                run_args, run_kwargs = mock_run.call_args
                assert isinstance(run_args[0], list)
                assert "wmic" == run_args[0][0]
                assert f"commandline like '%{service_name}%'" in run_args[0]

def test_restart_service_malicious_input():
    # Given the dictionary lookup, "malicious" input currently just returns an Error.
    result = restart_service("slow_loop\" & calc.exe & \"")
    assert "Error: No restart command defined" in result
