import sys
import os
import time
import subprocess

PROJECT_ROOT = r"C:\Sentinel_Project"
VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe")

def start_slow_loop():
    print("[INIT] Starting Sentinel v15.0 Slow Loop (Oracles)...")
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT};{os.path.join(PROJECT_ROOT, 'kronos_repo')}"
    return subprocess.Popen([VENV_PYTHON, os.path.join(PROJECT_ROOT, "sentinel_slow_loop.py")], env=env, cwd=PROJECT_ROOT)

def start_fast_loop():
    print("[INIT] Starting Sentinel v15.0 Fast Loop (Execution Engine)...")
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_ROOT
    return subprocess.Popen([VENV_PYTHON, os.path.join(PROJECT_ROOT, "chat_gemma.py")], env=env, cwd=PROJECT_ROOT)

if __name__ == "__main__":
    # 1. Start Slow Loop first to ensure cache is being populated
    slow_proc = start_slow_loop()
    time.sleep(10) # Give oracles a moment to initialize
    
    # 2. Start Fast Loop (Engine)
    fast_proc = start_fast_loop()
    
    print("[SUCCESS] Sentinel v15.0 Trading System fully initiated.")
    
    try:
        while True:
            time.sleep(5)
            if slow_proc.poll() is not None:
                print("[ERROR] Slow Loop died. Restarting...")
                slow_proc = start_slow_loop()
            if fast_proc.poll() is not None:
                print("[ERROR] Fast Loop died. Restarting...")
                fast_proc = start_fast_loop()
    except KeyboardInterrupt:
        print("[SHUTDOWN] Terminating trading processes...")
        slow_proc.terminate()
        fast_proc.terminate()
        print("[SYSTEM] Halted.")
