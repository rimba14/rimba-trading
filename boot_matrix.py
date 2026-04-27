"""
boot_matrix.py - ADAPTIVE SENTINEL MASTER BOOTSTRAPPER (v16.8)
Unified ignition sequence for decoupled microservices.
"""

import subprocess
import sys
import time
import signal
import logging
import os

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [BOOT_MATRIX] %(message)s')

# Core Matrix Scripts
CORE_SCRIPTS = [
    'hermes_orchestrator.py',
    'sentinel_slow_loop.py',
    'chat_gemma.py',
    'profit_manager.py'
]

def ignite_matrix():
    """Ignites all core microservices concurrently."""
    print("\n" + "="*60)
    print("IGNITING ADAPTIVE SENTINEL MATRIX (v16.8)")
    print("="*60)
    
    running_processes = []
    
    # Ensure current directory is in PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))

    for script in CORE_SCRIPTS:
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script)
        
        if not os.path.exists(script_path):
            logging.error(f"Script not found: {script}. Skipping...")
            continue
            
        logging.info(f"Igniting {script}...")
        try:
            # Use sys.executable to ensure same VENV is used
            proc = subprocess.Popen(
                [sys.executable, script_path],
                env=env,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            running_processes.append((script, proc))
            # Staggered boot to prevent CPU spikes and resource contention
            time.sleep(3) 
        except Exception as e:
            logging.error(f"Failed to ignite {script}: {e}")

    print(f"\n[SUCCESS] Matrix ignition sequence complete. {len(running_processes)} services active.")
    print("Press Ctrl+C to initiate Graceful Shutdown (SRE Kill Switch).")
    print("="*60 + "\n")

    try:
        while True:
            # Lifecycle Management: Monitor for dead processes
            for i, (name, proc) in enumerate(running_processes):
                retcode = proc.poll()
                if retcode is not None:
                    logging.warning(f"🚨 [PROCESS_EXIT] {name} died (Exit Code: {retcode}). Attempting auto-restart...")
                    new_proc = subprocess.Popen(
                        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), name)],
                        env=env,
                        cwd=os.path.dirname(os.path.abspath(__file__))
                    )
                    running_processes[i] = (name, new_proc)
            
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n" + "═"*60)
        print("🛑 SRE KILL SWITCH ACTIVATED: Initiating Graceful Shutdown")
        print("═"*60)
        
        for name, proc in running_processes:
            logging.info(f"Terminating {name} (PID: {proc.pid})...")
            proc.terminate()
            
        # Wait for all processes to close to prevent orphans
        for name, proc in running_processes:
            try:
                proc.wait(timeout=5)
                logging.info(f"Safe exit confirmed for {name}.")
            except subprocess.TimeoutExpired:
                logging.warning(f"Force killing {name} (Process did not terminate gracefully).")
                proc.kill()
        
        print("\n[SYSTEM] All engines halted. Matrix offline.")
        print("="*60)

if __name__ == "__main__":
    ignite_matrix()
