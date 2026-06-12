import json
import os
import logging
from typing import Dict, Any
from gitagent_types import CognitiveState, RuntimeTelemetry

logger = logging.getLogger("StrategyLogger")

class StrategyExecutionLogger:
    """
    Continuous state accumulator tracking full-stack trade context lifecycles.
    Dumps atomic transaction snapshots post-exit to automate Level 88 forensics.
    """
    def __init__(self, ticket_id: str, diagnostics_path: str = "shap_diagnostics/"):
        self.ticket_id = ticket_id
        self.output_file = os.path.join(diagnostics_path, f"trade_anatomy_{ticket_id}.json")
        self.trade_state_log: Dict[str, Any] = {}

    def capture_entry_cognitive_state(self, state: CognitiveState) -> None:
        self.trade_state_log["entry_metrics"] = {
            "probability_vector": state.raw_probability_vector,
            "adjusted_conviction": state.adjusted_conviction,
            "information_activity_ratio": state.activity_ratio,
            "order_flow_bocpd_probability": state.bocpd_prob,
            "wasserstein_cluster_index": state.wasserstein_idx,
            "volatility_ratio": state.volatility_ratio,
            "ofi_velocity": state.ofi_velocity
        }

    def capture_runtime_telemetry(self, telemetry: RuntimeTelemetry) -> None:
        if "trajectory" not in self.trade_state_log:
            self.trade_state_log["trajectory"] = []
        self.trade_state_log["trajectory"].append({
            "step_bar_idx": telemetry.bar_step,
            "floating_unrealized_pnl": telemetry.current_pnl,
            "matrix_condition_number": telemetry.condition_number,
            "feature_shap_importance": telemetry.shaps,
            "price": telemetry.price,
            "sl": telemetry.sl,
            "tp": telemetry.tp,
            "hmm_state": telemetry.hmm_state,
            "conviction": telemetry.conviction
        })

    def write_atomic_anatomy_report(self, definitive_exit_mechanism: str, mt5_retcode: int) -> bool:
        self.trade_state_log["exit_metrics"] = {
            "exit_mechanism": definitive_exit_mechanism,
            "mt5_return_code": mt5_retcode
        }
        try:
            os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
            with open(self.output_file, 'w') as f:
                json.dump(self.trade_state_log, f, indent=2)
            logger.info(f"SRE Forensic Snapshot saved successfully for Ticket {self.ticket_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to record atomic anatomy report payload: {str(e)}")
            return False
