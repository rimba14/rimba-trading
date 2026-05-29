import subprocess
import time
import sys
import os
import logging

# Configuration
PROJECT_ROOT = r"C:\Sentinel_Project"
VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe")

# Define tasks: (Script Path, Name) - v28.1 Active Pipeline
TASKS = [
    (os.path.join(PROJECT_ROOT, "fastapi_sniper.py"), "EXECUTION_SNIPER"),
    (os.path.join(PROJECT_ROOT, "profit_manager.py"), "PROFIT_MANAGER"),
    (os.path.join(PROJECT_ROOT, "oxford_orchestrator.py"), "SLOW_LOOP_ORCHESTRATOR"),
    (os.path.join(PROJECT_ROOT, "agents", "risk_agent.py"), "RISK_AGENT")
]

import io as _io
def _get_utf8_stream():
    if getattr(sys.stdout, 'encoding', '').lower() == 'utf-8':
        return sys.stdout
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        return sys.stdout
    except Exception:
        return _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

_UTF8_STREAM = _get_utf8_stream()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WATCHDOG] %(message)s',
    force=True,
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_ROOT, "watchdog.log"), encoding="utf-8"),
        logging.StreamHandler(_UTF8_STREAM)
    ]
)

def exorcise_legacy_processes():
    """Rule 1 & 2: Singular RAM Dominance & Ruthless Purge (v28.1)"""
    import psutil
    target_scripts = ["fastapi_sniper.py", "profit_manager.py", "oxford_orchestrator.py", "risk_agent.py", "sentinel_slow_loop.py"]
    logging.info("[PHASE 0] Starting Environment Exorcism...")
    
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if not cmdline: continue
            
            # If any target script is in the command line and it's not THIS process
            if any(script in " ".join(cmdline) for script in target_scripts) and proc.info['pid'] != current_pid:
                logging.warning(f"[PURGE] Terminating legacy daemon: PID {proc.info['pid']} ({' '.join(cmdline)})")
                proc.kill() # SIGKILL
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

def verify_ports_unbound():
    """Rule 3: Port Liberation (v28.1) — with 10s retry grace period"""
    import socket
    import time
    import psutil
    
    ports = [8000, 8001]
    max_retries = 10
    
    for port in ports:
        liberated = False
        for attempt in range(max_retries):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("0.0.0.0", port))
                    liberated = True
                    break
                except socket.error:
                    # Find who is holding the port
                    holder = "Unknown"
                    for conn in psutil.net_connections():
                        if conn.laddr.port == port:
                            try:
                                p = psutil.Process(conn.pid)
                                holder = f"PID {conn.pid} ({p.name()})"
                            except psutil.NoSuchProcess:
                                holder = f"PID {conn.pid} (Dead)"
                            break
                    
                    logging.warning(f"[PORT_BUSY] Port {port} held by {holder}. Retry {attempt+1}/{max_retries}...")
                    time.sleep(1)
        
        if not liberated:
            logging.critical(f"[PORT_BLOCK] Port {port} is STUBBORNLY held by {holder}. Exorcism failed.")
            sys.exit(1)
            
    logging.info("[PHASE 0] Ports 8000/8001 liberated.")

def launch_process(script_path, name):
    logging.info(f"Launching {name}: {script_path}")
    # Set PYTHONPATH to project root for imports
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_ROOT
    env["PYTHONIOENCODING"] = "utf-8" # Rule 4: Universal Enforcement
    return subprocess.Popen([VENV_PYTHON, script_path], cwd=PROJECT_ROOT, env=env)

def main():
    logging.info("ADAPTIVE SENTINEL v28.1 Ironclad CADES Supervisor Active.")
    
    # Phase 0: Pre-Flight Environment Exorcism
    exorcise_legacy_processes()
    verify_ports_unbound()
    
    processes = {}
    
    # Initial Launch
    for script, name in TASKS:
        if not os.path.exists(script):
            logging.error(f"[MISSING] {name} target script not found: {script}")
            continue
        processes[name] = {
            "path": script,
            "proc": launch_process(script, name)
        }

    try:
        while True:
            time.sleep(5)
            for name, data in processes.items():
                poll = data["proc"].poll()
                if poll is not None:
                    logging.critical(f"{name} died (Exit Code: {poll}). Restarting in 3 seconds...")
                    time.sleep(3)
                    processes[name]["proc"] = launch_process(data["path"], name)
    except KeyboardInterrupt:
        logging.info("Shutting down Sentinel processes...")
        for name, data in processes.items():
            data["proc"].terminate()
        logging.info("Watchdog Terminated.")

if __name__ == "__main__":
    main()

class ArcticDBClientWrapper:
    def __init__(self, arctic_instance):
        self.arctic = arctic_instance
        # ensure oracle_cache library exists
        if "oracle_cache" not in self.arctic.list_libraries():
            self.arctic.create_library("oracle_cache")
        self.lib = self.arctic["oracle_cache"]

    def read_latest_timestamp(self, key: str) -> dict:
        try:
            df = self.lib.read(key).data
            if df is None or df.empty:
                return {}
            # Convert last row of DataFrame to a dictionary
            last_row = df.iloc[-1]
            return last_row.to_dict()
        except Exception:
            return {}

def verify_regime_matrix_integrity(db_client, asset_symbol: str) -> bool:
    """
    Evaluates condition number sensitivity of our transition matrices.
    Acts as a proactive circuit breaker prior to real-time risk deterioration.
    """
    try:
        regime_payload = db_client.read_latest_timestamp(f"{asset_symbol}_regime_metrics")
        print(f"[DEBUG GATING] regime_payload for {asset_symbol}: {regime_payload}")
        cond_num = regime_payload.get("regime_condition_number", 1.0)
        print(f"[DEBUG GATING] cond_num: {cond_num}")
        
        # Hard boundary: Matrix sensitivity degradation flags unstable states
        if cond_num > 15.0:
            # Proactively clamp the Epistemic Entry Gate to risk-off (0.95)
            return False 
        return True
    except Exception as e:
        print(f"[DEBUG GATING] Exception in verification: {e}")
        # Failsafe: if we can't read/verify, return True (no block)
        return True

