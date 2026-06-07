import json
import logging
import os
import time

# ==========================================
# IDIOT INDEX & MODULE DECAY THRESHOLDS
# ==========================================
# Time-to-Live (TTL) Evaluation Window
IDIOT_INDEX_EVAL_WINDOW_DAYS = 60 

# Macro Gate Thresholds
# If the Macro Gate vetoes trades that would have been profitable > 40% of the time, archive it.
MACRO_GATE_FALSE_POSITIVE_LIMIT = 0.40 

# Entropy Gate Thresholds
# If the Entropy Gate fails to maintain a positive Information Coefficient (Edge), archive it.
ENTROPY_GATE_MIN_IC = 0.05 

# SRE Asynchronous Processing
# Frequency at which process_retrospective_decision_logs() evaluates the decision_trails folder
RETROSPECTIVE_POLL_RATE_HOURS = 4 

MODULE_EXPIRY = {
    "entropy_gate": {"max_age_days": IDIOT_INDEX_EVAL_WINDOW_DAYS, "metric_metric": "rolling_ic", "threshold": ENTROPY_GATE_MIN_IC, "action": "DEACTIVATE"},
    "macro_gate": {"max_age_days": IDIOT_INDEX_EVAL_WINDOW_DAYS, "metric_metric": "false_positive_embargo_rate", "threshold": MACRO_GATE_FALSE_POSITIVE_LIMIT, "action": "QUARANTINE"},
    "zombie_hold_layer": {"max_age_days": 30, "metric_metric": "floating_recovery_convergence", "threshold": 0.10, "action": "REVIEW"}
}

def check_module_lifecycle(module_name: str, current_metric_value: float, module_creation_timestamp: float) -> bool:
    """
    Evaluates whether a module should be allowed to run based on the idiot index decay curve.
    Returns True if the module is healthy and should run.
    Returns False if the module has expired or breached threshold (fail-closed bypass).
    """
    if module_name not in MODULE_EXPIRY:
        return True # Unmanaged module
        
    rules = MODULE_EXPIRY[module_name]
    max_age_seconds = rules["max_age_days"] * 86400
    
    age = time.time() - module_creation_timestamp
    
    # 1. Max Age Check
    if age > max_age_seconds:
        logging.warning(f"[LIFECYCLE] {module_name} outlived max age window. Action: {rules['action']}. Bypassing.")
        _alert_hermes_to_archive(module_name, "MAX_AGE_EXCEEDED")
        return False
        
    # 2. Performance Threshold Check
    # For entropy_gate and zombie_hold_layer, lower metrics might be worse.
    # We will assume a simple rule where falling below the threshold is bad for positive metrics,
    # and rising above is bad for negative metrics (like false_positive_embargo_rate).
    
    if rules["metric_metric"] == "false_positive_embargo_rate":
        if current_metric_value > rules["threshold"]:
            logging.warning(f"[LIFECYCLE] {module_name} breached {rules['metric_metric']} > {rules['threshold']}. Bypassing.")
            _alert_hermes_to_archive(module_name, "PERFORMANCE_BREACH")
            return False
    else:
        if current_metric_value < rules["threshold"]:
            logging.warning(f"[LIFECYCLE] {module_name} breached {rules['metric_metric']} < {rules['threshold']}. Bypassing.")
            _alert_hermes_to_archive(module_name, "PERFORMANCE_BREACH")
            return False
            
    return True

def _alert_hermes_to_archive(module_name: str, reason: str):
    """Writes a signal for Hermes to archive dependencies."""
    signal_dir = os.path.join(os.path.dirname(__file__), "data", "pending_diagnostics")
    os.makedirs(signal_dir, exist_ok=True)
    
    payload = {
        "type": "DECAY_WARNING",
        "module": module_name,
        "reason": reason,
        "action": "ARCHIVE_DEPENDENCIES",
        "timestamp": time.time()
    }
    filepath = os.path.join(signal_dir, f"DECAY_WARNING_{module_name}_{int(time.time())}.json")
    try:
        with open(filepath, "w") as f:
            json.dump(payload, f)
    except Exception as e:
        logging.error(f"Failed to alert Hermes: {e}")
