import json
import os
import logging
from typing import Dict, Any

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

    def capture_entry_cognitive_state(self, raw_probability_vector: list, adjusted_conviction: float, activity_ratio: float, bocpd_prob: float, wasserstein_idx: int, volatility_ratio: float = 0.0, ofi_velocity: float = 0.0) -> None:
        self.trade_state_log["entry_metrics"] = {
            "probability_vector": raw_probability_vector,
            "adjusted_conviction": adjusted_conviction,
            "information_activity_ratio": activity_ratio,
            "order_flow_bocpd_probability": bocpd_prob,
            "wasserstein_cluster_index": wasserstein_idx,
            "volatility_ratio": volatility_ratio,
            "ofi_velocity": ofi_velocity
        }

    def capture_runtime_telemetry(self, bar_step: int, current_pnl: float, condition_number: float, shaps: Dict[str, float], price: float = 0.0, sl: float = 0.0, tp: float = 0.0, hmm_state: str = "UNKNOWN", conviction: float = 0.0) -> None:
        if "trajectory" not in self.trade_state_log:
            self.trade_state_log["trajectory"] = []
        self.trade_state_log["trajectory"].append({
            "step_bar_idx": bar_step,
            "floating_unrealized_pnl": current_pnl,
            "matrix_condition_number": condition_number,
            "feature_shap_importance": shaps,
            "price": price,
            "sl": sl,
            "tp": tp,
            "hmm_state": hmm_state,
            "conviction": conviction
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
