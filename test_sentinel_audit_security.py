import unittest
from unittest.mock import patch, MagicMock
import subprocess
import sentinel_audit

class TestSentinelAuditSecurity(unittest.TestCase):

    @patch('subprocess.run')
    def test_run_command_shell_false(self, mock_run):
        # Mocking subprocess.run return value
        mock_run.return_value = MagicMock(returncode=0, stdout="test output", stderr="")

        cmd = ["ls", "-l"]
        desc = "Test list directory"

        sentinel_audit.run_command(cmd, desc)

        # Verify subprocess.run was called with shell=False
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0], cmd)
        self.assertFalse(kwargs.get('shell', True))

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('builtins.open', unittest.mock.mock_open(read_data="clean content"))
    def test_audit_calls_lists(self, mock_exists, mock_run):
        # Mocking subprocess.run to avoid actual execution
        mock_run.return_value = MagicMock(returncode=0, stdout="Claude Code CLI not found", stderr="")
        # Mocking os.path.exists to simulate test files being found or not
        mock_exists.return_value = True

        sentinel_audit.audit()

        # Verify all calls to subprocess.run used lists and shell=False
        for call in mock_run.call_args_list:
            args, kwargs = call
            self.assertIsInstance(args[0], list)
            self.assertFalse(kwargs.get('shell', True))

if __name__ == '__main__':
    unittest.main()
