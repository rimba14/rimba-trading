"""
boot_matrix.py - ADAPTIVE SENTINEL MASTER BOOTSTRAPPER (v17.2 Cloud-Native Build)
Unified ignition sequence for decoupled microservices with RAM-locked LLM verification.
"""

import subprocess
import sys
import time
import signal
import logging
import os
import requests
from dotenv import load_dotenv

# Load configuration
load_dotenv("C:\\Sentinel_Project\\.env")

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [BOOT_MATRIX] %(message)s')

def check_llm_status():
    """Directive 1: LLM Endpoint Pre-Flight Audit (v17.2)"""
    endpoint = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434") + "/api/tags"
    target_model = os.getenv("REASONING_MODEL", "qwen2.5-coder:3b")
    
    logging.info(f"[SYSTEM] Auditing Local LLM Endpoint: {endpoint}...")
    try:
        response = requests.get(endpoint, timeout=5)
        if response.status_code == 200:
            models = [m['name'] for m in response.json().get('models', [])]
            # Check for exact match or :latest tag
            if target_model in models or f"{target_model}:latest" in models:
                logging.info(f"\033[92m[SUCCESS] Local LLM Server (Ollama) is reachable. Model '{target_model}' READY.\033[0m")
                return True
            else:
                logging.error(f"Model '{target_model}' not found in Ollama library. Found: {models}")
        else:
            logging.error(f"Ollama returned status code {response.status_code}")
    except Exception as e:
        logging.error(f"Connection Refused: {e}")
    
    print("\033[91m" + "═"*60)
    print("[FATAL] SRE Pre-Flight Audit Failed.")
    print(f"Please ensure Ollama is running and model '{target_model}' is pulled.")
    print("Command: ollama pull " + target_model)
    print("The Ignition Sequence has been halted to prevent Fail-Safe conviction flatlines.")
    print("═"*60 + "\033[0m")
    return False

# Core Matrix Scripts (Updated for v17.2 naming)
CORE_SCRIPTS = [
    'hermes_orchestrator.py',
    'sentinel_slow_loop.py',
    'chat_gemma.py',
    'profit_manager.py'
]

def ignite_matrix():
    """Ignites all core microservices concurrently as headless daemon processes."""
    print("\n" + "="*60)
    print("IGNITING ADAPTIVE SENTINEL MATRIX (v17.2 - CLOUD-NATIVE)")
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
            # v17.2 Directive: Run as headless daemon (no new console window)
            proc = subprocess.Popen(
                [sys.executable, script_path],
                env=env,
                cwd=os.path.dirname(os.path.abspath(__file__)),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            running_processes.append((script, proc))
            # Staggered boot to prevent CPU spikes
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
                        cwd=os.path.dirname(os.path.abspath(__file__)),
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
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
            
        # Wait for all processes to close
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
    if check_llm_status():
        ignite_matrix()
    else:
        sys.exit(1)
