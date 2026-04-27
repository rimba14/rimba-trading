import sys
import os
import time
import subprocess
import multiprocessing

# Inject project path
sys.path.insert(0, r"C:\Sentinel_Project")

def start_slow_loop():
    print("[INIT] Starting Slow Loop (Oracles)...")
    env = os.environ.copy()
    env["PYTHONPATH"] = r"C:\Sentinel_Project\kronos_repo;C:\Sentinel_Project"
    subprocess.Popen([r"C:\Sentinel_Project\venv\Scripts\python.exe", r"C:\Sentinel_Project\sentinel_slow_loop.py"], env=env)

def run_executor(symbol, core_id):
    import vantage_execute_v13
    executor = vantage_execute_v13.VantageExecutorV13()
    executor.run_fast_loop(symbol, core_id)

if __name__ == "__main__":
    # 1. Start Slow Loop
    start_slow_loop()
    time.sleep(5) 
    
    import vantage_execute_v13
    processes = []
    for i, symbol in enumerate(vantage_execute_v13.WATCHLIST):
        p = multiprocessing.Process(target=run_executor, args=(symbol, i % multiprocessing.cpu_count()), daemon=True)
        p.start()
        processes.append(p)
        time.sleep(0.5) # Stagger start to prevent init collisions
        
    print(f"[SUCCESS] Sentinel v13.0 fully initiated on {len(processes)} cores.")
    
    try:
        for p in processes: p.join()
    except KeyboardInterrupt:
        import MetaTrader5 as mt5
        mt5.shutdown()
        print("[SHUTDOWN] System halted.")
