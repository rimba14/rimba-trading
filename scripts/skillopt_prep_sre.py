import os
import json
import random
from datetime import datetime
from typing import List, Dict, Any

class SkillOptDataPreparer:
    def __init__(self, pending_dir: str, archive_dir: str, output_root: str):
        self.pending_dir = pending_dir
        self.archive_dir = archive_dir
        self.output_root = output_root
        
    def extract_and_parse_logs(self) -> List[Dict[str, Any]]:
        task_dataset: List[Dict[str, Any]] = []
        
        # Ingest files from both active pending diagnostics and historical autopsies
        target_dirs = [self.pending_dir, self.archive_dir]
        for target_dir in target_dirs:
            if not os.path.exists(target_dir):
                continue
            for file_name in os.listdir(target_dir):
                if not file_name.endswith('.json'):
                    continue
                file_path = os.path.join(target_dir, file_name)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        ticket = json.load(f)
                    
                    # Core Parameter Extraction & Context Boundary Compaction
                    ticket_id = ticket.get("ticket_id", f"TICKET_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{random.randint(100,999)}")
                    error_sig = ticket.get("error_signature", ticket.get("message", "UNKNOWN_RUNTIME_EXCEPTION"))
                    
                    # Ingest adjacent codebase context and code graphs safely
                    affected_code = ticket.get("code_snapshot", "")
                    metrics_snapshot = ticket.get("telemetry", {})
                    
                    context_block = (
                        f"Target Module: {ticket.get('file_path', 'vantage_execute.py')}\n"
                        f"System Metrics at Failure: {json.dumps(metrics_snapshot)}\n"
                        f"Code Graph Function Snapshot:\n{affected_code}"
                    )
                    
                    # Map the target validation gate target metric
                    target_pass_criteria = ticket.get("validation_criteria", ["COMPILATION_SUCCESSFUL", "CALMAR_RATIO_OPTIMIZED"])
                    
                    task_dataset.append({
                        "id": ticket_id,
                        "question": error_sig,
                        "context": context_block,
                        "answers": target_pass_criteria if isinstance(target_pass_criteria, list) else [target_pass_criteria]
                    })
                except Exception as ex:
                    print(f"[-] Processing breakdown for {file_name}: {ex}")
        return task_dataset

    def split_and_write_dataset(self, tasks: List[Dict[str, Any]], train_ratio: float = 0.7, val_ratio: float = 0.2):
        # Enforce Chronological Split to eradicate look-ahead data leaking bias
        tasks.sort(key=lambda x: x['id']) 
        
        total = len(tasks)
        if total == 0:
            print("[!] Warning: Global SRE tracking buffer reads empty. Ingesting structural test mock data.")
            # Injecting placeholder baseline calibration nodes if empty
            tasks = [{
                "id": "MOCK_SRE_001",
                "question": "MT5 Error 10016: TRADE_RETCODE_INVALID_STOPS",
                "context": "def execute_stop(): return stop_distance < min_stops_level",
                "answers": ["ATR_BUFFER_EXPANDED"]
            }]
            total = len(tasks)

        train_end = int(total * train_ratio)
        val_end = train_end + int(total * val_ratio)
        
        splits = {
            "train": tasks[:train_end] if train_end > 0 else tasks,
            "val": tasks[train_end:val_end] if train_end < total else tasks,
            "test": tasks[val_end:] if val_end < total else tasks
        }
        
        for name, items in splits.items():
            dir_path = os.path.join(self.output_root, name)
            os.makedirs(dir_path, exist_ok=True)
            with open(os.path.join(dir_path, "items.json"), "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2)
            print(f"[+] SkillOpt Boundary Split Generated: {dir_path}/items.json (Nodes: {len(items)})")

if __name__ == "__main__":
    preparer = SkillOptDataPreparer(
        pending_dir="C:\\Sentinel_Project\\pending_diagnostics",
        archive_dir="C:\\Sentinel_Project\\sre_autopsy_history",
        output_root="C:\\Sentinel_Project\\data\\skillopt_sre"
    )
    data = preparer.extract_and_parse_logs()
    preparer.split_and_write_dataset(data)
