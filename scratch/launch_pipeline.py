import subprocess
import time
import os
import sys

PROJECT_ROOT = r"C:\Sentinel_Project"
VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe")

def launch_process(name, cmd):
    print(f"[LAUNCH] Starting {name}...")
    # Use CREATE_NEW_CONSOLE to open a new window for each script so the user can see them
    # and they don't block each other or this script.
    # 0x00000010 is CREATE_NEW_CONSOLE
    try:
        subprocess.Popen(cmd, creationflags=0x00000010, cwd=PROJECT_ROOT)
        print(f"[OK] {name} launched.")
    except Exception as e:
        print(f"[ERROR] Failed to launch {name}: {e}")

def main():
    # 1. Start MT5
    mt5_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    if os.path.exists(mt5_path):
        print("[LAUNCH] Starting MT5...")
        subprocess.Popen([mt5_path])
        time.sleep(5) # Wait for MT5 to warm up
    else:
        print("[WARN] MT5 path not found at default location.")

    # 2. Start Machine B Components (Execution)
    launch_process("Profit Manager", [VENV_PYTHON, "profit_manager.py"])
    time.sleep(2)
    launch_process("FastAPI Sniper", [VENV_PYTHON, "fastapi_sniper.py"])
    time.sleep(2)

    # 3. Start Machine A Components (Cognition)
    launch_process("Hermes Orchestrator", [VENV_PYTHON, "hermes_orchestrator.py"])
    time.sleep(2)
    launch_process("Sentinel Slow Loop", [VENV_PYTHON, "sentinel_slow_loop.py"])

    print("\n[SUCCESS] Sentinel v17.9 Pipeline engaged.")
    print("Check the newly opened console windows for live logs.")

if __name__ == "__main__":
    main()
