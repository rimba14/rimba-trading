import pytest
from unittest.mock import patch, MagicMock
import json
import re
import runpy
import logging
import synthetic_ping

def test_fire_synthetic_ping_no_webhook_url(caplog):
    caplog.set_level(logging.INFO, logger="SyntheticPing")
    with patch('synthetic_ping.DISCORD_WEBHOOK_URL', None):
        synthetic_ping.fire_synthetic_ping()
        assert "[ERROR] DISCORD_WEBHOOK_URL not found in .env" in caplog.text

def test_fire_synthetic_ping_empty_webhook_url(caplog):
    caplog.set_level(logging.INFO, logger="SyntheticPing")
    with patch('synthetic_ping.DISCORD_WEBHOOK_URL', ""):
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

        # Extract JSON from the content code block
        json_match = re.search(r'```json\n(.*?)\n```', payload['content'], re.DOTALL)
        assert json_match is not None
        signal_payload = json.loads(json_match.group(1))

        assert signal_payload['symbol'] == "EURUSD"
        assert signal_payload['direction'] == "BUY"
        assert signal_payload['conviction'] == 0.99
        assert signal_payload['hmm_state'] == "BULL"
        assert signal_payload['calculated_lot_size'] == 0.01
        assert signal_payload['timestamp'] == 1600000000
        assert signal_payload['version'] == "v17.5-PROD"

        assert "Synthetic Ping fired across the Discord Bridge" in caplog.text

@patch('synthetic_ping.requests.post')
def test_fire_synthetic_ping_success_200(mock_post, caplog):
    caplog.set_level(logging.INFO, logger="SyntheticPing")
    with patch('synthetic_ping.DISCORD_WEBHOOK_URL', 'http://fake-url.com'):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        synthetic_ping.fire_synthetic_ping()

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

def test_main_execution(caplog):
    caplog.set_level(logging.INFO, logger="SyntheticPing")
    with patch.dict('os.environ', {'DISCORD_WEBHOOK_URL': 'http://fake.com'}), \
         patch('requests.post') as mock_post:
        mock_post.return_value = MagicMock(status_code=204)
        # We need to ensure DISCORD_WEBHOOK_URL in the module is updated.
        # Since runpy.run_path will re-execute the module, it will call load_dotenv()
        # and then DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
        runpy.run_path('synthetic_ping.py', run_name='__main__')
        assert "Firing synthetic signal for EURUSD..." in caplog.text
