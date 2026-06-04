import os

log_file = "C:/Sentinel_Project/engine_stdout.txt"
if os.path.exists(log_file):
    print("Reading engine_stdout.txt...")
    with open(log_file, 'r', encoding='utf-16le', errors='ignore') as f:
        lines = f.readlines()
    print(f"Total lines: {len(lines)}")
    
    # Let's print any lines matching CL-OIL or position id or trade
    matches = []
    for i, line in enumerate(lines):
        if "CL-OIL" in line or "1314" in line or "trade" in line.lower() or "order" in line.lower() or "exit" in line.lower():
            matches.append((i, line.strip()))
            
    print(f"Found {len(matches)} matching lines:")
    for idx, m in matches[-30:]: # Print last 30 matches
        print(f"Line {idx}: {m}")
else:
    print("engine_stdout.txt not found.")
