import os
import json
import time
import logging

DIAGNOSTICS_DIR = r"C:\Sentinel_Project\pending_diagnostics"
DELEGATED_TASKS_DIR = r"C:\Sentinel_Project\delegated_sandbox"

os.makedirs(DIAGNOSTICS_DIR, exist_ok=True)
os.makedirs(DELEGATED_TASKS_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def monitor_and_delegate():
    """
    Pattern 4: Isolated Sandbox Architecture.
    Monitors pending diagnostics and delegates them to sub-agents via isolated tasking.
    """
    files = [f for f in os.listdir(DIAGNOSTICS_DIR) if f.endswith('.json')]
    
    for f in files:
        diag_path = os.path.join(DIAGNOSTICS_DIR, f)
        try:
            with open(diag_path, 'r') as file:
                payload = json.load(file)
            
            # Format the payload for the Subagent Sandbox
            task_id = f"sandbox_task_{int(time.time())}_{f}"
            sandbox_payload = {
                "directive": "SUBAGENT_DELEGATION",
                "task_id": task_id,
                "target_file": payload.get("target_file"),
                "anomaly_description": payload.get("anomaly_description", "Unknown Error"),
                "status": "AWAITING_SUBAGENT_EXECUTION"
            }
            
            sandbox_path = os.path.join(DELEGATED_TASKS_DIR, task_id)
            with open(sandbox_path, 'w') as out_f:
                json.dump(sandbox_payload, out_f, indent=4)
                
            logging.info(f"Delegated anomaly {f} to Sandbox Context -> {task_id}")
            
            # Remove from pending to prevent duplicate delegation
            os.remove(diag_path)
            
        except Exception as e:
            logging.error(f"Failed to delegate {f}: {e}")

if __name__ == "__main__":
    logging.info("Hermes Orchestrator (Sandbox Delegation Node) Started.")
    try:
        while True:
            monitor_and_delegate()
            time.sleep(5)
    except KeyboardInterrupt:
        logging.info("Orchestrator Shutdown.")
