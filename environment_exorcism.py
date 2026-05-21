import os
import sys
import subprocess
import socket
from logger_config import get_logger

log = get_logger("environment_exorcism")

DAEMONS = [
    "sentinel_slow_loop.py",
    "fastapi_sniper.py",
    "profit_manager.py",
    "mixts_router.py",
    "execution_node.py",
    "sentinel_dashboard.py"
]

def kill_legacy_daemons():
    log.info("[PHASE 0] Starting Environment Exorcism...")
    try:
        # Using tasklist and filtering for python.exe
        output = subprocess.check_output(["tasklist", "/v", "/fo", "csv", "/fi", "imagename eq python.exe"]).decode('utf-8', errors='ignore')
        lines = output.split('\n')
        for line in lines:
            for daemon in DAEMONS:
                if daemon in line:
                    # CSV format: "Image Name","PID","Session Name","Session#","Mem Usage","Status","User Name","CPU Time","Window Title"
                    parts = line.split('","')
                    if len(parts) > 1:
                        pid = parts[1].replace('"', '')
                        log.warning(f"[RULE 2] Forcefully terminating legacy daemon: {daemon} (PID: {pid})")
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)])
    except Exception as e:
        log.error(f"[FAIL] Rule 2 execution error: {e}")

def verify_ports():
    ports = [8000, 8001]
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            res = s.connect_ex(('127.0.0.1', port))
            if res == 0:
                log.error(f"[RULE 3] Port {port} is ALREADY BOUND. Liberation required.")
                # Attempt to find PID using port and kill it
                try:
                    netstat = subprocess.check_output(["netstat", "-ano"]).decode('utf-8')
                    for ns_line in netstat.strip().split('\n'):
                        if f":{port}" in ns_line and "LISTENING" in ns_line:
                            pid = ns_line.strip().split()[-1]
                            log.warning(f"[RULE 3] Killing process {pid} binding port {port}")
                            subprocess.run(["taskkill", "/F", "/PID", str(pid)])
                except:
                    pass
            else:
                log.info(f"[RULE 3] Port {port} is liberated.")

def apply_utf8():
    log.info("[RULE 4] Enforcing Universal UTF-8...")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    # sys.stdout.reconfigure is handled at entry points per Directive

if __name__ == "__main__":
    kill_legacy_daemons()
    verify_ports()
    apply_utf8()
    log.info("[OK] Environment Exorcism complete.")
