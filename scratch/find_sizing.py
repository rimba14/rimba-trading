import os
from pathlib import Path

root = Path("C:/Sentinel_Project")
print("Listing files containing 'medallion' or 'sizing' recursively...")
for p in root.rglob("*"):
    # skip venv
    if "venv" in str(p) or ".git" in str(p):
        continue
    if "medallion" in p.name.lower() or "sizing" in p.name.lower():
        print(f"Match: {p} (Size: {p.stat().st_size} bytes)")
