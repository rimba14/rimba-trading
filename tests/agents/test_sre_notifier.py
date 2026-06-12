import pytest
import time
from unittest.mock import patch, MagicMock
from agents.sre_watchdog_mcp import SRENotifier

def test_sre_notifier_async_behavior():
    notifier = SRENotifier("http://example.com/webhook")

    with patch("requests.post") as mock_post:
        # Simulate network latency
        def slow_post(*args, **kwargs):
            time.sleep(0.5)
            return MagicMock()
        mock_post.side_effect = slow_post

        start_time = time.time()
        notifier.send_intervention_alert("Test async message")
        end_time = time.time()

        # The call should return almost immediately
        assert end_time - start_time < 0.1

        # We need to wait for the background thread to finish or shutdown the executor
        notifier.executor.shutdown(wait=True)

        # Verify requests.post was actually called
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://example.com/webhook"
        assert kwargs["json"]["embeds"][0]["description"] == "Test async message"

def test_sre_notifier_exception_handling():
    notifier = SRENotifier("http://example.com/webhook")

    with patch("requests.post", side_effect=Exception("Network failure")):
        with patch("logging.error") as mock_log:
            notifier.send_intervention_alert("Test failure message")
            notifier.executor.shutdown(wait=True)

            # Verify exception was logged
            mock_log.assert_called()
            assert "SRE Webhook Exception: Network failure" in mock_log.call_args[0][0]
