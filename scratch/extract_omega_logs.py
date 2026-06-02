import os
import re

LOG_DIR = "C:/sentinel_logs"

def search_logs():
    targets = ["1306172614", "1303723015", "1306704393"]
    log_files = [
        "fastapi_sniper_v2.log",
        "fastapi_sniper_v26.log",
        "fastapi_sniper_v26_err.log",
        "profit_manager_v20_4.log"
    ]
    
    print("=== COGNITIVE FORENSICS LOG EXTRACTOR ===")
    for filename in log_files:
        filepath = os.path.join(LOG_DIR, filename)
        if not os.path.exists(filepath):
            continue
            
        print(f"\nScanning: {filename}...")
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            
        for target in targets:
            print(f"  --> Target ID: {target}")
            matches = []
            for i, line in enumerate(lines):
                if target in line:
                    matches.append((i, line))
                    
            if not matches:
                print("      No matches.")
                continue
                
            print(f"      Found {len(matches)} occurrences.")
            # Print first 5 and last 5 occurrences to avoid log flooding
            if len(matches) <= 10:
                for idx, line in matches:
                    print(f"        Line {idx+1}: {line.strip()}")
            else:
                print("      First 5 occurrences:")
                for idx, line in matches[:5]:
                    print(f"        Line {idx+1}: {line.strip()}")
                print("      Last 5 occurrences:")
                for idx, line in matches[-5:]:
                    print(f"        Line {idx+1}: {line.strip()}")

if __name__ == "__main__":
    search_logs()
