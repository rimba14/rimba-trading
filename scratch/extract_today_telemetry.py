import os

LOG_DIR = "C:/sentinel_logs"

def search_today_broad():
    log_files = [f for f in os.listdir(LOG_DIR) if f.endswith(".log") or f.endswith(".txt")]
    
    print("=== BROAD TODAY'S NZDUSD SEARCH ===")
    for filename in log_files:
        filepath = os.path.join(LOG_DIR, filename)
        
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            
        matches = []
        for i, line in enumerate(lines):
            # Check for NZDUSD and May 18 14:4
            if "NZDUSD" in line and ("14:4" in line or "14:47" in line or "14:48" in line or "14:46" in line):
                matches.append((i, line))
                
        if matches:
            print(f"\nScanning: {filename}... Found {len(matches)} matches:")
            for idx, line in matches[:20]:
                print(f"        Line {idx+1}: {line.strip()}")

if __name__ == "__main__":
    search_today_broad()
