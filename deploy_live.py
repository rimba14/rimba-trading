import sys
import os
import time
import subprocess
import socket
import threading
import queue
import logging
import psutil
import MetaTrader5 as mt5

PROJECT_ROOT = r"C:\Sentinel_Project"
VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe")

# ANSI Colors
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_MAGENTA = "\033[35m"
COLOR_CYAN = "\033[36m"

def print_banner():
    banner = f"""
{COLOR_BOLD}{COLOR_MAGENTA}==========================================================================
 🚨 ADAPTIVE SENTINEL v28.1 - LIVE CAPITAL ORCHESTRATION & DEPLOYMENT 🚨
=========================================================================={COLOR_RESET}
    """
    print(banner)

# Queue for unified console logging
console_queue = queue.Queue()

def log_orchestrator(msg, level="info"):
    color = COLOR_CYAN if level == "info" else (COLOR_RED if level == "error" else COLOR_YELLOW)
    prefix = f"{COLOR_BOLD}{color}[ORCHESTRATOR]{COLOR_RESET}"
    console_queue.put(f"{prefix} {msg}")

def reader_thread(stream, prefix, color):
    """Reads lines from a subprocess stream and puts them in the console queue."""
    for line in iter(stream.readline, b''):
        decoded_line = line.decode('utf-8', errors='replace').rstrip()
        if decoded_line:
            console_queue.put(f"{color}{prefix}{COLOR_RESET} {decoded_line}")
    stream.close()

def exorcise_legacy_processes():
    """Step 1: Forcefully purge legacy processes to enforce Singular RAM Dominance."""
    log_orchestrator("Starting Singular RAM Dominance sweep...")
    target_scripts = ["fastapi_sniper.py", "profit_manager.py", "sentinel_slow_loop.py"]
    current_pid = os.getpid()
    purged_count = 0
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if not cmdline:
                continue
            cmd_str = " ".join(cmdline)
            if any(script in cmd_str for script in target_scripts) and proc.info['pid'] != current_pid:
                log_orchestrator(f"Terminating legacy process: PID {proc.info['pid']} ({cmd_str})", "warn")
                proc.kill() # Force kill
                purged_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
            
    if purged_count > 0:
        log_orchestrator(f"Purged {purged_count} legacy daemons successfully.")
    else:
        log_orchestrator("No legacy processes detected. RAM is clean.")

def verify_ports_unbound():
    """Step 1b: Verify Ports 8000 and 8001 are strictly unbound (Port Liberation)."""
    log_orchestrator("Verifying Ports 8000 and 8001 are liberated...")
    ports = [8000, 8001]
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
            except socket.error:
                log_orchestrator(f"Port {port} is strictly bound or held! Aborting boot.", "error")
                sys.exit(1)
    log_orchestrator("Ports 8000 and 8001 are successfully liberated.")

def run_self_certification():
    """Step 2: Programmatically run self_cert.py and abort on non-zero exit."""
    log_orchestrator("Initiating self-certification gate (self_cert.py)...")
    res = subprocess.run([VENV_PYTHON, "self_cert.py"], cwd=PROJECT_ROOT)
    if res.returncode != 0:
        log_orchestrator("Self-certification FAILED! Refusing to boot. Live Capital aborted.", "error")
        sys.exit(1)
    log_orchestrator("Self-certification PASSED successfully.")

def live_broker_handshake():
    """Step 3: Connect to MT5 and inspect the account server for Demo warning."""
    log_orchestrator("Performing live broker handshake...")
    if not mt5.initialize():
        log_orchestrator("Failed to initialize MT5! Refusing to boot.", "error")
        sys.exit(1)
        
    acc = mt5.account_info()
    if not acc:
        log_orchestrator("Failed to retrieve MT5 account info! Handshake failed.", "error")
        mt5.shutdown()
        sys.exit(1)
        
    server = acc.server
    log_orchestrator(f"MT5 Account Connected. Login: {acc.login} | Server: {server}")
    
    if "Demo" in server or "demo" in server.lower():
        warning_banner = f"""
{COLOR_BOLD}{COLOR_RED}==========================================================================
 ⚠️ WARNING: SYSTEM RUNNING ON DEMO SERVER ({server}) ⚠️
 The v28.1 Live Capital Constitution authorizes live execution.
 Please verify if this is paper-trading validation or actual deployment!
=========================================================================={COLOR_RESET}
        """
        console_queue.put(warning_banner)
    else:
        live_banner = f"""
{COLOR_BOLD}{COLOR_GREEN}==========================================================================
 ✅ SUCCESS: SYSTEM CONNECTED TO LIVE PRODUCTION SERVER ({server}) ✅
 v28.1 Ironclad CADES Constitution: Live Capital Mode ACTIVATED.
=========================================================================={COLOR_RESET}
        """
        console_queue.put(live_banner)
        
    mt5.shutdown()

def console_writer():
    """Outputs messages from the unified telemetry queue in real time."""
    while True:
        try:
            line = console_queue.get(timeout=0.1)
            print(line, flush=True)
            console_queue.task_done()
        except queue.Empty:
            continue

def main():
    print_banner()
    
    # Start console output thread
    writer = threading.Thread(target=console_writer, daemon=True)
    writer.start()
    
    time.sleep(0.5) # Give writer a moment to boot
    
    # Step 1: Purge & Liberation
    exorcise_legacy_processes()
    verify_ports_unbound()
    
    # Step 2: Self-Certification Gate
    run_self_certification()
    
    # Step 3: Live Broker Handshake & Security Check
    live_broker_handshake()
    
    log_orchestrator("All pre-flight gates successfully cleared. Commencing Daemon Ignition Sequence...")
    
    # Step 4: Daemon Ignition Sequence
    processes = []
    
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_ROOT
    env["PYTHONIOENCODING"] = "utf-8"
    
    # 1. fastapi_sniper.py
    log_orchestrator("Igniting Execution Bridge (fastapi_sniper.py)...")
    proc_sniper = subprocess.Popen(
        [VENV_PYTHON, "fastapi_sniper.py"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=PROJECT_ROOT, env=env
    )
    processes.append((proc_sniper, "FASTAPI_SNIPER", COLOR_YELLOW))
    
    # Give FastAPI 3 seconds to spin up and bind Port 8000
    time.sleep(3.0)
    
    # 2. profit_manager.py
    log_orchestrator("Igniting Capital Shield / Naked Sweep (profit_manager.py)...")
    proc_profit = subprocess.Popen(
        [VENV_PYTHON, "profit_manager.py"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=PROJECT_ROOT, env=env
    )
    processes.append((proc_profit, "PROFIT_MANAGER", COLOR_GREEN))
    
    # Give Profit Manager 2 seconds to establish socket
    time.sleep(2.0)
    
    # 3. sentinel_slow_loop.py
    log_orchestrator("Igniting Alpha Factory Slow Loop (sentinel_slow_loop.py)...")
    proc_slow = subprocess.Popen(
        [VENV_PYTHON, "sentinel_slow_loop.py"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=PROJECT_ROOT, env=env
    )
    processes.append((proc_slow, "SLOW_LOOP", COLOR_BLUE))
    
    # Launch reader threads for all processes (stdout and stderr)
    for proc, name, color in processes:
        # stdout reader
        t_out = threading.Thread(
            target=reader_thread,
            args=(proc.stdout, f"[{name}]", color),
            daemon=True
        )
        t_out.start()
        # stderr reader
        t_err = threading.Thread(
            target=reader_thread,
            args=(proc.stderr, f"[{name}_ERR]", COLOR_RED + COLOR_BOLD),
            daemon=True
        )
        t_err.start()
        
    log_orchestrator("==================================================")
    log_orchestrator("🎉 ALL DAEMONS ONLINE! WATCHTOWER TELEMETRY ACTIVE")
    log_orchestrator("==================================================")
    
    try:
        while True:
            # Check if any process has died
            for proc, name, color in processes:
                exit_code = proc.poll()
                if exit_code is not None:
                    log_orchestrator(f"CRITICAL: Daemon {name} has terminated with exit code {exit_code}!", "error")
                    # Terminate others and exit
                    for p, n, _ in processes:
                        if p.poll() is None:
                            p.terminate()
                    sys.exit(1)
            time.sleep(1.0)
    except KeyboardInterrupt:
        log_orchestrator("KeyboardInterrupt received. Terminating all active Sentinel processes cleanly...")
        for proc, name, _ in processes:
            if proc.poll() is None:
                log_orchestrator(f"Terminating {name}...")
                proc.terminate()
        log_orchestrator("Watchdog shutting down. All daemons successfully terminated.")
        sys.exit(0)

if __name__ == "__main__":
    main()
