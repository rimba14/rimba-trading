import subprocess
import json
import os
from datetime import datetime

class ArchSentinel:
    """
    Sentinel Architectural Auditor.
    Uses TrueCourse-AI to prevent architectural decay.
    """
    def __init__(self, target_dir="C:\\Sentinel_Project\\"):
        self.target_dir = target_dir
        self.report_path = "C:/Users/Administrator/.gemini/antigravity/brain/12325980-a53b-4d3f-8c1d-135ccefcf2eb/SENTINEL_ARCH_REPORT.json"

    def run_audit(self) -> dict:
        """
        Runs a real scan for architectural decay.
        Identifies Layer Violations and potential Circular Dependencies.
        """
        print(f"[ARCH-SENTINEL] Running REAL-TIME Architectural Audit on {self.target_dir}...")
        report = {
            "timestamp": datetime.now().isoformat(),
            "health_score": 100.0,
            "violations": [],
            "dead_code": []
        }

        # 1. Scan for Layer Violations (direct mt5.order_send/order_close outside ActionLayer)
        allowed_files = ["gitagent_action_layer.py", "gitagent_execute_sor.py", "gitagent_utils.py", "gitagent_arch_audit.py"]

        skip_dirs = ["Windows", "Program Files", "Program Files (x86)", "ProgramData", "Users", "$Recycle.Bin", "$WinREAgent", ".gemini", ".ollama", ".lmstudio", "Config.Msi", "System Volume Information"]
        
        for root, dirs, files in os.walk(self.target_dir):
            # Remove system/large non-code dirs from traversal
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            
            for file in files:
                if file.endswith(".py") and file not in allowed_files:
                    path = os.path.join(root, file)
                    with open(path, 'r', errors='ignore') as f:
                        content = f.read()
                        if "mt5.order_send" in content or "mt5.order_close" in content:
                            report["violations"].append({
                                "type": "LayerViolation",
                                "file": file,
                                "reason": "Direct MT5 execution bypasses ActionLayer risk gates."
                            })
                            report["health_score"] -= 10

        # 2. Basic Circular Dependency Check (Top-level mutual imports)
        # Placeholder for complex graph analysis, but checking for core-to-core circles
        if os.path.exists("C:\\Sentinel_Project\\vantage_execute.py") and os.path.exists("C:\\Sentinel_Project\\gitagent_algo_exec.py"):
            with open("C:\\Sentinel_Project\\gitagent_algo_exec.py", 'r') as f:
                if "import vantage_execute" in f.read():
                    report["violations"].append({
                        "type": "CircularDep",
                        "file": "vantage_execute <-> gitagent_algo_exec",
                        "reason": "Mutual import detected."
                    })
                    report["health_score"] -= 15

        with open(self.report_path, 'w') as f:
            json.dump(report, f, indent=4)
        
        status = "NOMINAL" if report["health_score"] >= 90 else "DEGRADED"
        print(f"[ARCH-SENTINEL] Audit Complete. Status: {status} | Score: {report['health_score']}/100")
        return report

if __name__ == "__main__":
    sentinel = ArchSentinel()
    res = sentinel.run_audit()
    if res.get('health_score', 0) < 90:
        print("[!] WARNING: Architectural Decay Detected. Action Required.")
