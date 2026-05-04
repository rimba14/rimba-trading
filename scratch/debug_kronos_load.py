import sys
import os
from pathlib import Path
import torch

KRONOS_REPO_PATH = r"C:\Sentinel_Project\kronos_repo"
sys.path.append(KRONOS_REPO_PATH)

try:
    from model.kronos import KronosTokenizer
    print("Success: from model.kronos import KronosTokenizer")
    
    tokenizer_path = "NeoQuasar/Kronos-Tokenizer-base"
    print(f"Attempting to load tokenizer from {tokenizer_path}...")
    
    # Try to import safetensors manually to see if it helps
    try:
        import safetensors
        print("safetensors is available")
    except ImportError:
        print("safetensors is NOT available")

    tokenizer = KronosTokenizer.from_pretrained(tokenizer_path)
    print("Success: KronosTokenizer.from_pretrained")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
