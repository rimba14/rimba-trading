import os
import sys
import time
import subprocess
import psutil
import MetaTrader5 as mt5
from constants import SENTINEL_VERSION

def initialize_git_handshake():
    """Calculate and write the active git hash to secure handshake."""
    print("\n[INIT] Initializing version handshake...")
    try:
        active_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip().decode("utf-8")
        hash_file = "C:/Sentinel_Project/data/active_git_hash.txt"
        os.makedirs(os.path.dirname(hash_file), exist_ok=True)
        with open(hash_file, "w") as f:
            f.write(active_hash)
        print(f"[BOOT] Initialized active version handshake signature: {active_hash}")
    except Exception as e:
        print(f"[BOOT] Warning: Could not write active version handshake signature: {e}")

def purge_legacy_daemons():
    """Phase 1: The Purge (Wall 1 Process Dominance) - Purging legacy trading daemons."""
    print("\n[PHASE 1] Purging legacy trading daemons...")
    current_pid = os.getpid()
    purged_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.pid == current_pid:
                continue
            cmd = proc.info.get('cmdline') or []
            cmd_str = " ".join(cmd)
            # Find and SIGKILL fastapi_sniper, profit_manager, sentinel_slow_loop, risk_agent
            if any(daemon in cmd_str for daemon in ['sentinel_slow_loop', 'fastapi_sniper', 'profit_manager', 'risk_agent']):
                print(f"[PURGE] Forcefully terminating legacy process {proc.pid}: {proc.name()} ({cmd_str})")
                proc.kill()
                purged_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    print(f"[PHASE 1] Purged {purged_count} legacy process instances.")

def run_self_certification():
    """Phase 2: Integrity Self-Certification Check."""
    print("\n[PHASE 2] Running self-certification suite...")
    res = subprocess.run([sys.executable, "self_cert.py"], capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        print("[CRITICAL ERROR] Self-Certification Suite FAILED! Cold-boot aborted to prevent capital risk.")
        print(res.stdout)
        print(res.stderr)
        sys.exit(1)
    print("[PHASE 2] Self-Certification suite PASSED.")

def perform_broker_handshake():
    """Phase 3: Broker Handshake."""
    print("\n[PHASE 3] Initiating Broker Handshake...")
    if not mt5.initialize():
        print("[CRITICAL ERROR] MetaTrader 5 Initialization FAILED. Cold-boot aborted.")
        sys.exit(1)
        
    acc_info = mt5.account_info()
    if acc_info is None:
        print("[CRITICAL ERROR] Failed to query MT5 broker account info. Cold-boot aborted.")
        sys.exit(1)
        
    print(f"[HANDSHAKE] Connected successfully to MT5 Terminal.")
    print(f"[HANDSHAKE] Broker:  {acc_info.company}")
    print(f"[HANDSHAKE] Server:  {acc_info.server}")
    print(f"[HANDSHAKE] Account: {acc_info.login}")
    
    server_upper = str(acc_info.server).upper()
    if "DEMO" in server_upper:
        print("\n" + "!"*80)
        print(" [WARNING] SERVER DETECTED AS DEMO SERVER. LIVE CAPITAL CANNOT BE DEPLOYED!")
        print("!"*80 + "\n")
    else:
        print("\n" + "="*80)
        print(" [WARNING] ALERT: LIVE CAPITAL PRODUCTION SERVER ACTIVE. PREPARE FOR DEPLOYMENT!")
        print("="*80 + "\n")
    
    mt5.shutdown()

def launch_trading_daemons():
    """Phase 4: Daemon Ignition."""
    print("\n[PHASE 4] Launching trading daemons...")
    
    # 1. fastapi_sniper (The Execution Bridge / Wall 4 & 5)
    print("[IGNITION] Starting fastapi_sniper.py (Execution Bridge)...")
    fastapi_proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "fastapi_sniper:app", "--port", "8000", "--host", "127.0.0.1"])
    
    # 1b. agents/risk_agent.py (The Sovereign Risk Agent / Wall 4 on Port 8001)
    print("[IGNITION] Starting risk_agent.py (Portfolio Guardian / Port 8001)...")
    risk_proc = subprocess.Popen([sys.executable, "agents/risk_agent.py"])
    
    # 2. profit_manager.py (The Naked Kill Switch)
    print("[IGNITION] Starting profit_manager_v28_34.py (Naked Kill Switch)...")
    profit_proc = subprocess.Popen([sys.executable, "profit_manager_v28_34.py"])
    
    print("[IGNITION] Waiting 5 seconds for execution bridges and shields to stabilize...")
    time.sleep(5)
    
    # 3. sentinel_slow_loop.py (The Alpha Factory)
    print("[IGNITION] Starting sentinel_slow_loop.py (Alpha Factory)...")
    slow_proc = subprocess.Popen([sys.executable, "sentinel_slow_loop.py"])
    
    return fastapi_proc, risk_proc, profit_proc, slow_proc

def main():
    print("="*60)
    print(f"      [BOOT] SENTINEL {SENTINEL_VERSION} MASTER ORCHESTRATOR COLD-BOOT")
    print("="*60)

    initialize_git_handshake()
    purge_legacy_daemons()
    run_self_certification()
    perform_broker_handshake()

    fastapi_proc, risk_proc, profit_proc, slow_proc = launch_trading_daemons()

    print("\n" + "="*60)
    print("      [OK] ADAPTIVE SENTINEL TRADING DEPLOYED SUCCESSFULLY")
    print("="*60 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Orchestrator intercepted shutdown signal. Terminating background trading daemons...")
        daemons = [
            ("fastapi_sniper", fastapi_proc),
            ("risk_agent", risk_proc),
            ("profit_manager", profit_proc),
            ("sentinel_slow_loop", slow_proc)
        ]
        for name, p in daemons:
            try:
                print(f"[SHUTDOWN] Terminating process {name} (PID {p.pid})...")
                p.terminate()
            except Exception as e:
                print(f"[SHUTDOWN] Failed to terminate {name}: {e}")
        print("[SHUTDOWN] System offline.")

if __name__ == '__main__':
    main()
