import sys
import unittest
import os
from unittest.mock import patch, MagicMock

# Manually load the module instead of relying on normal imports
import importlib.util
spec = importlib.util.spec_from_file_location("vectorbt_researcher_mcp", os.path.abspath(os.path.join(os.path.dirname(__file__), '../../agents/vectorbt_researcher_mcp.py')))

# Prevent errors
sys.modules['MetaTrader5'] = MagicMock()
sys.modules['gitagent_utils'] = MagicMock()

vectorbt_researcher_mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vectorbt_researcher_mcp)

send_research_webhook = vectorbt_researcher_mcp.send_research_webhook
DISCORD_WEBHOOK = vectorbt_researcher_mcp.DISCORD_WEBHOOK

class TestVectorBTResearcherMCP(unittest.TestCase):

    @patch('requests.post')
    def test_send_research_webhook_success(self, mock_post):
        # Arrange
        symbol = "BTCUSD"
        config = "10_50_MA"
        sharpe = 2.5
        total_ret = 0.15

        # Act
        send_research_webhook(symbol, config, sharpe, total_ret)

        # Assert
        mock_post.assert_called_once()

        # Check payload and URL
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], DISCORD_WEBHOOK)

        kwargs = call_args[1]
        self.assertIn('json', kwargs)
        self.assertEqual(kwargs['timeout'], 10)

        payload = kwargs['json']
        self.assertIn('embeds', payload)
        self.assertEqual(len(payload['embeds']), 1)

        embed = payload['embeds'][0]
        self.assertEqual(embed['title'], "🔬 QUANT RESEARCH: New Edge Detected")
        self.assertEqual(
            embed['description'],
            f"**Symbol:** `{symbol}`\n**Config:** `{config}`\n**Sharpe:** `{sharpe:.2f}`\n**Return:** `{total_ret:.2%}`"
        )
        self.assertEqual(embed['color'], 0x3498DB)
        self.assertEqual(embed['footer']['text'], "Adaptive Sentinel v15.1 | VectorBT Engine")

    @patch('requests.post')
    def test_send_research_webhook_exception(self, mock_post):
        # Arrange
        mock_post.side_effect = Exception("Connection Error")
        symbol = "BTCUSD"
        config = "10_50_MA"
        sharpe = 2.5
        total_ret = 0.15

        # Act
        try:
            send_research_webhook(symbol, config, sharpe, total_ret)
            # The function handles the exception silently with pass, so it shouldn't raise here
        except Exception as e:
            self.fail(f"send_research_webhook raised an exception unexpectedly: {e}")

        # Assert
        mock_post.assert_called_once()

if __name__ == '__main__':
    unittest.main()
