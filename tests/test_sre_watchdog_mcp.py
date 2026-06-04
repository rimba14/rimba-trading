import pytest
from unittest.mock import patch, MagicMock
from agents.sre_watchdog_mcp import restart_service

def test_restart_service_success():
    # Mock subprocess.run for the kill command
    with patch("agents.sre_watchdog_mcp.subprocess.run") as mock_run:
        # Mock subprocess.Popen for the restart command
        with patch("agents.sre_watchdog_mcp.subprocess.Popen") as mock_popen:
            # Mock notifier
            with patch("agents.sre_watchdog_mcp.notifier.send_intervention_alert") as mock_notifier:
                result = restart_service("slow_loop")

                assert "Service slow_loop restart initiated." == result

                # Assert run was called for killing the process
                mock_run.assert_called_once()
                run_args = mock_run.call_args[0][0]
                assert "wmic" in run_args

                # Assert Popen was called
                mock_popen.assert_called_once()
                args, kwargs = mock_popen.call_args
                assert kwargs["shell"] is False
                assert isinstance(args[0], list)
                assert "SENTINEL RESTART: slow_loop" in args[0]
                assert "call venv\\Scripts\\activate && python sentinel_slow_loop.py" in args[0][-1]

                # Assert notifier was called
                mock_notifier.assert_called_once()
                assert "Restarted service `slow_loop`" in mock_notifier.call_args[0][0]

def test_restart_service_unknown_service():
    result = restart_service("unknown_service")

    assert "Error: No restart command defined for service 'unknown_service'." == result

def test_restart_service_exception():
    # Mock subprocess.Popen to raise an Exception
    with patch("agents.sre_watchdog_mcp.subprocess.Popen", side_effect=Exception("Test Error")):
        # Mock subprocess.run to not interfere
        with patch("agents.sre_watchdog_mcp.subprocess.run"):
            result = restart_service("fast_loop")

            assert "Error during restart: Test Error" in result
