import sys
import os

print(f"Python Version: {sys.version}")
print(f"Current Directory: {os.getcwd()}")

try:
    import torch
    print(f"Torch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device: {torch.cuda.get_device_name(0)}")
except Exception as e:
    print(f"ERROR importing torch: {e}")
    import traceback
    traceback.print_exc()
