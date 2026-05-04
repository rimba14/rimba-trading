import sys
from pathlib import Path
sys.path.append(r"C:\Sentinel_Project")
from math_meta_model import MathMetaModel

mm = MathMetaModel()
# Test BTCUSD-like values
# [XGB, Kronos, HMM, FAISS, Macro_Sent, Macro_Risk, Catalyst]
p = mm.predict_conviction("BTCUSD", 0.5, 0.71, "RANGE", 0.88)
print(f"BTCUSD Meta-Conviction: {p:.6f}")
