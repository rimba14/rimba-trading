import time
import os
import subprocess

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=False, capture_output=True, text=True)
        return res.stdout
    except:
        return ""

print("Agent 15 | Live Market Dashboard | 60s Cycle")
while True:
    print("\n" + "="*80)
    print(f"Cycle Start: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # Run scan
    print("Scanning neural convictions...")
    scan_out = run_cmd(["python", "C:\\Sentinel_Project\\manual_scan.py"])
    if "TOP NEURAL OPPORTUNITIES" in scan_out:
        parts = scan_out.split("--- TOP NEURAL OPPORTUNITIES ---")
        print(parts[1].split("Exit code")[0])
    
    # Run audit
    print("\nAuditing active positions...")
    audit_out = run_cmd(["python", "C:\\Sentinel_Project\\audit_positions.py"])
    if "TICKET" in audit_out:
        print(audit_out.split("Exit code")[0])
    
    print(f"\nSleeping 60 seconds...")
    time.sleep(60)
