import sys
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

# Mocking modules that might not be available or have side effects
sys.modules['MetaTrader5'] = MagicMock()
sys.modules['vectorbt'] = MagicMock()
sys.modules['xgboost'] = MagicMock()
sys.modules['git_arctic'] = MagicMock()
sys.modules['medallion_trainer'] = MagicMock()
mock_config = MagicMock()
mock_config.BROKER_SUFFIX = ".pro"
sys.modules['sentinel_config'] = mock_config
sys.modules['gitagent_utils'] = MagicMock()
sys.modules['gitagent_algebraic_manifold'] = MagicMock()

import vectorbt_researcher_mcp

class TestVectorBTResearcherRoot(unittest.TestCase):
    @patch('vectorbt_researcher_mcp.pd.concat')
    @patch('vectorbt_researcher_mcp.send_research_webhook')
    @patch('vectorbt_researcher_mcp.PurgedKFold')
    @patch('vectorbt_researcher_mcp.calculate_dsr')
    def test_run_parameter_sweep_name_error_capture(self, mock_dsr, mock_pkf, mock_webhook, mock_concat):
        # Setup mocks
        mock_mt5 = sys.modules['MetaTrader5']
        mock_mt5.initialize.return_value = True
        mock_mt5.copy_rates_from_pos.return_value = [
            [0,0,0,0,100.0], [0,0,0,0,101.0], [0,0,0,0,102.0]
        ]
        mock_mt5.TIMEFRAME_M15 = 15

        mock_vbt = sys.modules['vectorbt']
        mock_pf = MagicMock()
        mock_vbt.Portfolio.from_signals.return_value = mock_pf
        mock_pf.sharpe_ratio.return_value = pd.Series([1.5])
        mock_pf.returns.return_value = pd.Series([0.01, 0.02])

        mock_xgb = sys.modules['xgboost']
        mock_model = MagicMock()
        mock_xgb.XGBClassifier.return_value = mock_model
        mock_model.predict_proba.return_value = np.array([[0.4, 0.6]] * 3)

        mock_pkf_inst = mock_pkf.return_value
        mock_pkf_inst.split.return_value = [(np.array([0, 1]), np.array([2]))]

        mock_dsr.return_value = (0.99, 0.5)

        # Mocking sharpe_df
        mock_sharpe_df = MagicMock()
        mock_concat.return_value = mock_sharpe_df
        mock_sharpe_df.values.flatten.return_value = np.array([1.5])
        mock_sharpe_df.groupby.return_value.quantile.return_value = pd.Series([1.5], index=[0])

        # Act
        result = vectorbt_researcher_mcp.run_parameter_sweep("EURUSD")

        # Assert
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['best_config'], '0')

if __name__ == '__main__':
    unittest.main()
