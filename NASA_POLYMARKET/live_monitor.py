import time
import os
from main_runner import run_satellite_oracle, run_weather_oracle

def start_monitor(interval_seconds: int = 900): # Default 15 mins
    print(f"🕯️ [MONITOR] Starting Live Fire Watch (Interval: {interval_seconds}s)")
    print(f"🕯️ [MONITOR] Tracking Satellite Anomaly Deltas...")
    
    try:
        while True:
            # 1. Satellite Fire Scan
            run_satellite_oracle()
            
            # 2. Weather Consensus Scan
            run_weather_oracle()
            
            print(f"\n[SLEEP] Waiting {interval_seconds}s for next intelligence sweep...")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\n👋 [MONITOR] Fire Watch stopped safely.")

if __name__ == "__main__":
    # Start the monitoring loop
    start_monitor()
