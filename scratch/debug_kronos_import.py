import sys
import os
from pathlib import Path

KRONOS_REPO_PATH = r"C:\Sentinel_Project\kronos_repo"
sys.path.append(KRONOS_REPO_PATH)

print(f"Path: {sys.path}")

try:
    import model.kronos
    print("Success: import model.kronos")
    from model.kronos import KronosTokenizer
    print("Success: from model.kronos import KronosTokenizer")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
