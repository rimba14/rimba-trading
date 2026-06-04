import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os

# Mock MetaTrader5 before importing deploy_live
mock_mt5 = MagicMock()
sys.modules["MetaTrader5"] = mock_mt5

import deploy_live

class TestDeployLive(unittest.TestCase):

    @patch("deploy_live.subprocess.check_output")
    @patch("deploy_live.os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("deploy_live.psutil.process_iter")
    @patch("deploy_live.os.getpid")
    @patch("deploy_live.subprocess.run")
    @patch("deploy_live.mt5")
    @patch("deploy_live.subprocess.Popen")
    @patch("deploy_live.time.sleep")
    @patch("deploy_live.sys.exit")
    def test_main_success_flow(self, mock_exit, mock_sleep, mock_popen, mock_mt5_in_module,
                               mock_run, mock_getpid, mock_process_iter, mock_file_open,
                               mock_makedirs, mock_check_output):

        # Setup mocks
        mock_check_output.return_value = b"test_hash"
        mock_getpid.return_value = 1234

        # Mock legacy processes
        proc1 = MagicMock()
        proc1.pid = 5678
        proc1.info = {'cmdline': ['python', 'sentinel_slow_loop.py']}
        proc1.name.return_value = "python"

        mock_process_iter.return_value = [proc1]

        # Mock self-cert success
        mock_run.return_value = MagicMock(returncode=0)

        # Mock MT5
        mock_mt5_in_module.initialize.return_value = True
        mock_acc_info = MagicMock()
        mock_acc_info.company = "Test Broker"
        mock_acc_info.server = "Test Server"
        mock_acc_info.login = 12345
        mock_mt5_in_module.account_info.return_value = mock_acc_info

        # Mock subprocess.Popen
        mock_popen.return_value = MagicMock(pid=999)

        # We need to break the infinite loop in main
        # The loop is while True: time.sleep(1)
        # We can make sleep raise an exception to exit the loop
        mock_sleep.side_effect = [None, KeyboardInterrupt]

        # Run main
        deploy_live.main()

        # Verify Phase 1 (Git handshake)
        mock_check_output.assert_called_with(["git", "rev-parse", "HEAD"])
        mock_file_open.assert_called_with("C:/Sentinel_Project/data/active_git_hash.txt", "w")
        mock_file_open().write.assert_called_with("test_hash")

        # Verify Phase 2 (Purge)
        proc1.kill.assert_called_once()

        # Verify Phase 3 (Self-cert)
        mock_run.assert_called()
        self.assertEqual(mock_run.call_args[0][0][1], "self_cert.py")

        # Verify Phase 4 (MT5)
        mock_mt5_in_module.initialize.assert_called_once()
        mock_mt5_in_module.account_info.assert_called_once()
        mock_mt5_in_module.shutdown.assert_called_once()

        # Verify Phase 5 (Ignition)
        self.assertEqual(mock_popen.call_count, 4)

        # Verify termination on KeyboardInterrupt
        for name, p in [("fastapi_sniper", mock_popen()), ("risk_agent", mock_popen()), ("profit_manager", mock_popen()), ("sentinel_slow_loop", mock_popen())]:
             p.terminate.assert_called()

if __name__ == "__main__":
    unittest.main()
