import sys
from pathlib import Path
sys.path.append(r"C:\Sentinel_Project")
from math_meta_model import MathMetaModel

mm = MathMetaModel()
# Test LTCUSD parameters
# Z_XGB=0.5, Z_KRONOS=0.80, HMM="BULL"(1), FAISS=0.85, MacroSent=0.35, Risk=0.18, Catalyst=0.75
p = mm.predict_conviction("LTCUSD", 0.5, 0.80, "BULL", 0.85)
print(f"LTCUSD Meta-Conviction: {p:.6f}")
