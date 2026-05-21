import pytest
import subprocess
from agents.sre_watchdog_mcp import restart_service

def test_restart_service_success(mocker):
    # Mock subprocess.Popen
    mock_popen = mocker.patch("agents.sre_watchdog_mcp.subprocess.Popen")
    # Mock notifier
    mock_notifier = mocker.patch("agents.sre_watchdog_mcp.notifier.send_intervention_alert")

    result = restart_service("slow_loop")

    assert "Service slow_loop restart initiated." == result

    # Assert Popen was called
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    assert "shell" in kwargs
    assert kwargs["shell"] is True
    assert "SENTINEL RESTART: slow_loop" in args[0]
    assert "python sentinel_slow_loop.py" in args[0]

    # Assert notifier was called
    mock_notifier.assert_called_once()
    assert "Restarted service `slow_loop`" in mock_notifier.call_args[0][0]

def test_restart_service_unknown_service():
    result = restart_service("unknown_service")

    assert "Error: No restart command defined for service 'unknown_service'." == result

def test_restart_service_exception(mocker):
    # Mock subprocess.Popen to raise an Exception
    mock_popen = mocker.patch("agents.sre_watchdog_mcp.subprocess.Popen", side_effect=Exception("Test Error"))

    result = restart_service("fast_loop")

    assert "Error during restart: Test Error" in result
