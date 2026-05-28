from pathlib import Path

path = Path(r"C:\Sentinel_Project\math_meta_model.py")
content = path.read_text(encoding="utf-8")

# Fix predict_conviction signature
old_sig = 'def predict_conviction(self, symbol: str, xgb_prob: float, kronos_prob: float, hmm_state: str, faiss_sim: float) -> float:'
new_sig = 'def predict_conviction(self, symbol: str, features: dict) -> float:'
content = content.replace(old_sig, new_sig)

# Fix hmm_encoded
old_hmm = 'hmm_encoded = self._encode_hmm(hmm_state)'
new_hmm = 'hmm_encoded = self._encode_hmm(features.get("hmm_state", "RANGE"))'
content = content.replace(old_hmm, new_hmm)

# Fix X_live
old_xlive = """        X_live = np.array([[
            float(xgb_prob), 
            float(kronos_prob), 
            float(hmm_encoded), 
            float(faiss_sim),
            float(macro_sent),
            float(black_swan_risk),
            float(catalyst)
        ]])"""

new_xlive = """        X_live = np.array([[
            float(features.get("xgb_p", 0.5)), 
            float(features.get("kronos_p", 0.5)), 
            float(hmm_encoded), 
            float(features.get("faiss_sim", 0.0)),
            float(macro_sent),
            float(black_swan_risk),
            float(catalyst),
            float(features.get("frac_diff", 0.0)),
            float(features.get("fft_amp_1", 0.0)),
            float(features.get("fft_amp_2", 0.0)),
            float(features.get("fft_amp_3", 0.0)),
            float(features.get("cs_rank", 0.5)),
        ]])"""

# Note: X_live search might fail due to whitespace. I'll use a more flexible search.
import re
content = re.sub(r'X_live = np\.array\(\[\[.*?\]\]\)', new_xlive, content, flags=re.DOTALL)

# Fix dummy fit to 12 features
old_dummy = """            X_dummy = np.array([[0.5, 0.5, 0, 0.0, 0.0, 0.0, 0.0], [0.8, 0.8, 1, 0.8, 0.1, 0.1, 0.2]])"""
new_dummy = """            X_dummy = np.zeros((2, 12))
            X_dummy[0] = [0.5, 0.5, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5]
            X_dummy[1] = [0.8, 0.8, 1, 0.8, 0.1, 0.1, 0.2, 0.5, 0.1, 0.08, 0.05, 0.8]"""
content = content.replace(old_dummy, new_dummy)

# Update log messages
content = content.replace("Initialized baseline dummy regressor model.", "Initialized baseline dummy regressor model (12 features).")

path.write_text(content, encoding="utf-8")
print("Successfully patched math_meta_model.py")
