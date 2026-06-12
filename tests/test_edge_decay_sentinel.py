import os
import sys
import json
import unittest
import numpy as np

# Ensure path imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import edge_decay_sentinel
from pre_execution_gate import run_all_gates, DecayGuardVetoException, GateContext
from agent_quarantine import registry

class TestEdgeDecaySentinel(unittest.TestCase):
    def setUp(self):
        # Backup existing state file if any
        self.state_file = "oracle_cache/edge_decay_state.json"
        self.backup_path = self.state_file + ".bak"
        if os.path.exists(self.state_file):
            try:
                os.rename(self.state_file, self.backup_path)
            except Exception as e:
                print(f"Failed to backup existing state file: {e}")
            
    def tearDown(self):
        # Restore backup
        if os.path.exists(self.state_file):
            try:
                os.remove(self.state_file)
            except:
                pass
        if os.path.exists(self.backup_path):
            try:
                os.rename(self.backup_path, self.state_file)
            except:
                pass
            
        # Clean up diagnostic file
        diag_file = "pending_diagnostics/decay_breach.json"
        if os.path.exists(diag_file):
            try:
                os.remove(diag_file)
            except:
                pass

    def test_mbb_bootstrap_runs_cleanly(self):
        # 1. Test Moving Block Bootstrap return shape and values
        baseline = edge_decay_sentinel.get_baseline_profile('v30.98')
        daily_returns = baseline['daily_return_distribution']
        
        paths = edge_decay_sentinel.moving_block_bootstrap(
            daily_returns, block_size=3, num_paths=100, path_len=30
        )
        self.assertEqual(paths.shape, (100, 30))
        
        # Test percentile calculation
        p5, p50, p95 = edge_decay_sentinel.compute_drawdown_percentiles(paths)
        self.assertEqual(len(p5), 30)
        self.assertEqual(len(p95), 30)
        self.assertTrue(np.all(p95 >= p5))

    def test_sentinel_sweep_creates_payload(self):
        # 2. Test full sentinel execution and payload serialization
        metrics, payload = edge_decay_sentinel.run_edge_decay_sentinel('v30.98')
        self.assertTrue(os.path.exists(self.state_file))
        
        self.assertEqual(payload['master_version'], 'v30.98')
        self.assertIn(payload['global_status'], ['NORMAL', 'SOFT_BREACH', 'HARD_BREACH'])
        self.assertIn('module_tier', payload)
        self.assertIn('agent_tier', payload)

    def test_pre_execution_gate_hard_breach_veto(self):
        # 3. Force a HARD_BREACH state to test pre-execution gate veto
        forced_payload = {
            "timestamp": "2026-06-11T12:00:00Z",
            "master_version": "v30.98",
            "global_status": "HARD_BREACH",
            "module_tier": {
                "Directive_Meridian": "HARD_BREACH"
            },
            "agent_tier": {
                "MixTS_v1": "QUARANTINED"
            },
            "diagnosis": "REGIME_SHIFT"
        }
        
        # Write state atomically
        edge_decay_sentinel.atomic_write_json(self.state_file, forced_payload)
        
        # Call run_all_gates and assert DecayGuardVetoException
        with self.assertRaises(DecayGuardVetoException):
            context = GateContext(
                symbol="EURUSD", direction="BUY", asset_class="FOREX",
                regime="BULL", ticket_ref="12345", kelly_lots=0.1,
                entry_price=1.1000, sl_distance=0.0100, tp_distance=0.0200,
                risk_usd=100.0, equity=10000.0, current_heat_usd=200.0,
                embargo_registry={}
            )
            run_all_gates(context)
            
        # Verify pending_diagnostics/decay_breach.json was generated
        diag_file = "pending_diagnostics/decay_breach.json"
        self.assertTrue(os.path.exists(diag_file))
        with open(diag_file, "r") as f:
            log_data = json.load(f)
        self.assertEqual(log_data['symbol'], "EURUSD")
        self.assertEqual(log_data['strategy'], "Directive_Meridian")

    def test_agent_quarantine_dynamic_filtering(self):
        # 4. Force quarantine on ddqn via MixTS_v1 status
        forced_payload = {
            "timestamp": "2026-06-11T12:00:00Z",
            "master_version": "v30.98",
            "global_status": "SOFT_BREACH",
            "module_tier": {
                "Directive_Meridian": "SOFT_BREACH"
            },
            "agent_tier": {
                "ddqn": "QUARANTINED",
                "hmm": "ACTIVE"
            },
            "diagnosis": "NORMAL"
        }
        edge_decay_sentinel.atomic_write_json(self.state_file, forced_payload)
        
        test_scores = {
            "ddqn": 0.85,
            "hmm": 0.60
        }
        
        filter_res = registry.filter_agents(test_scores)
        self.assertNotIn("ddqn", filter_res.filtered_scores)
        self.assertIn("hmm", filter_res.filtered_scores)
        self.assertIn("ddqn", filter_res.quarantined)

if __name__ == '__main__':
    unittest.main()
