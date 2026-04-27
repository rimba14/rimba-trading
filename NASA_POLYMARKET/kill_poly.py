import os
import psutil
import signal

def kill_poly_processes():
    current_pid = os.getpid()
    count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and any('live_monitor.py' in arg for arg in cmdline):
                    if proc.info['pid'] != current_pid:
                        print(f"Killing process {proc.info['pid']}: {' '.join(cmdline)}")
                        os.kill(proc.info['pid'], signal.SIGTERM)
                        count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    print(f"Terminated {count} instances of live_monitor.py.")

if __name__ == "__main__":
    kill_poly_processes()
