import sys
import os

sys.path.append(r"c:\Sentinel_Project")
print(f"Python Version: {sys.version}")

try:
    import torch
    print(f"Torch version: {torch.__version__}")
except Exception as e:
    print(f"ERROR importing torch: {e}")

try:
    from timesfm_internal.timesfm_2p5.timesfm_2p5_torch import TimesFM_2p5_200M_torch
    print("SUCCESS: Imported TimesFM_2p5_200M_torch")
except Exception as e:
    print(f"ERROR importing TimesFM: {e}")
    import traceback
    traceback.print_exc()
