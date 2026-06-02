import os
from pathlib import Path

root = Path("C:/Sentinel_Project")
print("Listing all files with .log or .jsonl extension in C:/Sentinel_Project recursively...")
for p in root.rglob("*.log"):
    # skip venv
    if "venv" in str(p) or ".git" in str(p):
        continue
    print(f"Log file: {p} (Size: {p.stat().st_size} bytes)")
    
for p in root.rglob("*.jsonl"):
    if "venv" in str(p) or ".git" in str(p):
        continue
    print(f"JSONL file: {p} (Size: {p.stat().st_size} bytes)")
