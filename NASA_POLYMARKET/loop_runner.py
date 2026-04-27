import os
import time
import subprocess
from datetime import datetime

def run_main():
    print(f"[{datetime.now()}] 🚀 Launching NASA Polymarket Cycle...")
    try:
        # Run the existing main_runner.py script
        result = subprocess.run(["python", "main_runner.py"], capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(f"⚠️ [STDERR] {result.stderr}")
    except Exception as e:
        print(f"❌ [CRITICAL] Failed to execute main_runner.py: {e}")

if __name__ == "__main__":
    print("=== NASA POLYMARKET LOOP RUNNER ===")
    while True:
        run_main()
        print(f"[{datetime.now()}] 💤 Sleeping for 300 seconds...")
        time.sleep(300) # Run every 5 minutes
