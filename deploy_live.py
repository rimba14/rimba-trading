import os
import sys
import time
import subprocess
import psutil
import MetaTrader5 as mt5

def main():
    print("="*60)
    print("      [BOOT] SENTINEL v28.27 MASTER ORCHESTRATOR COLD-BOOT")
    print("="*60)

    # -------------------------------------------------------------
    # Phase 1: The Purge (Wall 1 Process Dominance)
    # -------------------------------------------------------------
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

    # -------------------------------------------------------------
    # Phase 2: Integrity Self-Certification Check
    # -------------------------------------------------------------
    print("\n[PHASE 2] Running self-certification suite...")
    res = subprocess.run([sys.executable, "self_cert.py"], capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        print("[CRITICAL ERROR] Self-Certification Suite FAILED! Cold-boot aborted to prevent capital risk.")
        print(res.stdout)
        print(res.stderr)
        sys.exit(1)
    print("[PHASE 2] Self-Certification suite PASSED.")

    # -------------------------------------------------------------
    # Phase 3: Broker Handshake
    # -------------------------------------------------------------
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

    # -------------------------------------------------------------
    # Phase 4: Daemon Ignition
    # -------------------------------------------------------------
    print("\n[PHASE 4] Launching trading daemons...")
    
    # 1. fastapi_sniper (The Execution Bridge / Wall 4 & 5)
    print("[IGNITION] Starting fastapi_sniper.py (Execution Bridge)...")
    fastapi_proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "fastapi_sniper:app", "--port", "8000", "--host", "127.0.0.1"])
    
    # 1b. agents/risk_agent.py (The Sovereign Risk Agent / Wall 4 on Port 8001)
    print("[IGNITION] Starting risk_agent.py (Portfolio Guardian / Port 8001)...")
    risk_proc = subprocess.Popen([sys.executable, "agents/risk_agent.py"])
    
    # 2. profit_manager.py (The Naked Kill Switch)
    print("[IGNITION] Starting profit_manager_v25.py (Naked Kill Switch)...")
    profit_proc = subprocess.Popen([sys.executable, "profit_manager_v25.py"])
    
    print("[IGNITION] Waiting 5 seconds for execution bridges and shields to stabilize...")
    time.sleep(5)
    
    # 3. sentinel_slow_loop.py (The Alpha Factory)
    print("[IGNITION] Starting sentinel_slow_loop.py (Alpha Factory)...")
    slow_proc = subprocess.Popen([sys.executable, "sentinel_slow_loop.py"])
    
    print("\n" + "="*60)
    print("      [OK] ADAPTIVE SENTINEL TRADING DEPLOYED SUCCESSFULLY")
    print("="*60 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Orchestrator intercepted shutdown signal. Terminating background trading daemons...")
        for name, p in [("fastapi_sniper", fastapi_proc), ("risk_agent", risk_proc), ("profit_manager", profit_proc), ("sentinel_slow_loop", slow_proc)]:
            try:
                print(f"[SHUTDOWN] Terminating process {name} (PID {p.pid})...")
                p.terminate()
            except Exception as e:
                print(f"[SHUTDOWN] Failed to terminate {name}: {e}")
        print("[SHUTDOWN] System offline.")

if __name__ == '__main__':
    main()
