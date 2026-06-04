import os

LOG_DIR = "C:/sentinel_logs"

def search_cognitive_state():
    files = ["slow_loop_v26.log", "slow_loop_v17_9.log", "risk_agent_v26.log"]
    
    print("=== COGNITIVE STATE LOG SEARCH ===")
    for filename in files:
        filepath = os.path.join(LOG_DIR, filename)
        if not os.path.exists(filepath):
            continue
            
        print(f"\nScanning: {filename}...")
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            
        matches = []
        for i, line in enumerate(lines):
            # Check for SOLUSD and 11:00
            if "SOLUSD" in line and ("11:00" in line or "10:59" in line or "11:01" in line):
                matches.append((i, line))
                
        if not matches:
            print("      No matches around 11:00.")
            # Let's search generally for SOLUSD
            sol_matches = [i for i, l in enumerate(lines) if "SOLUSD" in l]
            print(f"      Total SOLUSD occurrences in file: {len(sol_matches)}")
            if sol_matches:
                print("      First 3 general SOLUSD matches:")
                for idx in sol_matches[:3]:
                    print(f"        Line {idx+1}: {lines[idx].strip()}")
            continue
            
        print(f"      Found {len(matches)} occurrences around 11:00:")
        for idx, line in matches:
            print(f"        Line {idx+1}: {line.strip()}")

if __name__ == "__main__":
    search_cognitive_state()
