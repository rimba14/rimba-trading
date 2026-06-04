import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

log_file = "C:/Sentinel_Project/engine_stdout.txt"
if os.path.exists(log_file):
    with open(log_file, 'r', encoding='utf-16le', errors='ignore') as f:
        print(f.read())
else:
    print("Not found.")
