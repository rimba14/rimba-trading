import pytest
from unittest.mock import patch, MagicMock
import json
import synthetic_ping
import logging

def test_fire_synthetic_ping_no_webhook_url(caplog):
    caplog.set_level(logging.INFO, logger="SyntheticPing")
    with patch('synthetic_ping.DISCORD_WEBHOOK_URL', None):
        synthetic_ping.fire_synthetic_ping()
        assert "[ERROR] DISCORD_WEBHOOK_URL not found in .env" in caplog.text

@patch('synthetic_ping.time.time')
@patch('synthetic_ping.requests.post')
def test_fire_synthetic_ping_success(mock_post, mock_time, caplog):
    caplog.set_level(logging.INFO, logger="SyntheticPing")
    mock_time.return_value = 1600000000.0
    with patch('synthetic_ping.DISCORD_WEBHOOK_URL', 'http://fake-url.com'):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        synthetic_ping.fire_synthetic_ping()

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == 'http://fake-url.com'
        assert 'json' in kwargs
        assert kwargs['timeout'] == 10

        payload = kwargs['json']
        assert 'content' in payload
        assert 'SYNTHETIC SRE SIGNAL INJECTION' in payload['content']
        assert '"symbol": "EURUSD"' in payload['content']
        assert '"timestamp": 1600000000' in payload['content']

        assert "Synthetic Ping fired across the Discord Bridge" in caplog.text

@patch('synthetic_ping.requests.post')
def test_fire_synthetic_ping_failure(mock_post, caplog):
    caplog.set_level(logging.INFO, logger="SyntheticPing")
    with patch('synthetic_ping.DISCORD_WEBHOOK_URL', 'http://fake-url.com'):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        synthetic_ping.fire_synthetic_ping()

        assert "[ERROR] Webhook failed with status: 400 | Reason: Bad Request" in caplog.text

@patch('synthetic_ping.requests.post')
def test_fire_synthetic_ping_exception(mock_post, caplog):
    caplog.set_level(logging.INFO, logger="SyntheticPing")
    with patch('synthetic_ping.DISCORD_WEBHOOK_URL', 'http://fake-url.com'):
        mock_post.side_effect = Exception("Connection Timeout")

        synthetic_ping.fire_synthetic_ping()

        assert "[CRITICAL] Error firing synthetic ping: Connection Timeout" in caplog.text
