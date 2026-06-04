import os

def check_file(filepath):
    if os.path.exists(filepath):
        print(f"\n--- Reading {filepath} ---")
        try:
            with open(filepath, 'r', encoding='utf-16le', errors='ignore') as f:
                content = f.read()
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if "CL-OIL" in line:
                    print(f"Line {i}: {line.strip()}")
        except Exception as e:
            print(f"Error: {e}")
            
check_file("C:/Sentinel_Project/market_scan_results.txt")
check_file("C:/Sentinel_Project/report_scan.txt")
check_file("C:/Sentinel_Project/scan_out.txt")
