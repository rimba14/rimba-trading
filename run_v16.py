import sys
import os
import time
import subprocess

PROJECT_ROOT = r"C:\Sentinel_Project"
VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe")

def launch_process(script_name, description):
    print(f"[INIT] Starting {description} ({script_name})...")
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_ROOT
    # Use start to launch in a new terminal window on Windows for visibility
    # return subprocess.Popen(["cmd", "/c", "start", f"Sentinel: {description}", VENV_PYTHON, os.path.join(PROJECT_ROOT, script_name)], env=env, cwd=PROJECT_ROOT)
    # Actually, for the AI to monitor, we want them in the same process tree or background
    return subprocess.Popen([VENV_PYTHON, os.path.join(PROJECT_ROOT, script_name)], env=env, cwd=PROJECT_ROOT)

if __name__ == "__main__":
    print("="*60)
    print("ADAPTIVE SENTINEL v16.9 - MASTER LAUNCHER")
    print("="*60)

    processes = {
        "Slow Loop": "sentinel_slow_loop.py",
        "Fast Loop": "chat_gemma.py",
        "Profit Manager": "profit_manager.py",
        "Hermes": "hermes_orchestrator.py"
    }

    running_procs = {}

    for desc, script in processes.items():
        running_procs[desc] = launch_process(script, desc)
        time.sleep(5) # Staggered boot

    print(f"\n[SUCCESS] Sentinel v16.9 Production Build fully initiated.")
    print(f"Monitoring {len(processes)} microservices. Press Ctrl+C to halt.")

    try:
        while True:
            time.sleep(10)
            for desc, proc in running_procs.items():
                if proc.poll() is not None:
                    print(f"[ERROR] {desc} died. Restarting...")
                    running_procs[desc] = launch_process(processes[desc], desc)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Terminating all Sentinel processes...")
        for desc, proc in running_procs.items():
            proc.terminate()
        print("[SYSTEM] All engines halted.")
