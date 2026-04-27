import subprocess
import time
import sys
import os
import logging

# Configuration
PROJECT_ROOT = r"C:\Sentinel_Project"
VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe")

# Define tasks: (Script Path, Name)
TASKS = [
    (os.path.join(PROJECT_ROOT, "run_v15.py"), "SENTINEL_LOOPS_V15"),
    (os.path.join(PROJECT_ROOT, "hermes_orchestrator.py"), "HERMES_ORCHESTRATOR"),
    (os.path.join(PROJECT_ROOT, "agents", "profit_manager_v15.py"), "PROFIT_MANAGER")
]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WATCHDOG] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_ROOT, "watchdog.log")),
        logging.StreamHandler(sys.stdout)
    ]
)

def launch_process(script_path, name):
    logging.info(f"Launching {name}: {script_path}")
    # Set PYTHONPATH to project root for imports
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_ROOT
    return subprocess.Popen([VENV_PYTHON, script_path], cwd=PROJECT_ROOT, env=env)

def main():
    logging.info("Adaptive Sentinel Supervisor Active.")
    processes = {}

    # Initial Launch
    for script, name in TASKS:
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
