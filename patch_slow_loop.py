import sys
from pathlib import Path

path = Path(r"C:\Sentinel_Project\sentinel_slow_loop.py")
content = path.read_text(encoding="utf-8")

# Fix the call to predict_conviction
old_call = 'p_val = _MATH_META_MODEL.predict_conviction(symbol, xgb_val, kronos_val, hmm_state, faiss_sim)'
new_call = 'p_val = _MATH_META_MODEL.predict_conviction(symbol, features)'
content = content.replace(old_call, new_call)

path.write_text(content, encoding="utf-8")
print("Successfully patched sentinel_slow_loop.py")
