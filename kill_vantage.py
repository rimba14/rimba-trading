import os
import psutil
import signal

def kill_vantage_processes():
    current_pid = os.getpid()
    count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Check if it's a python process
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and any('vantage_execute.py' in arg for arg in cmdline):
                    if proc.info['pid'] != current_pid:
                        print(f"Killing process {proc.info['pid']}: {' '.join(cmdline)}")
                        os.kill(proc.info['pid'], signal.SIGTERM)
                        count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    print(f"Terminated {count} instances of vantage_execute.py.")

if __name__ == "__main__":
    kill_vantage_processes()
