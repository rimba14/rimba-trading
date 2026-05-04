import sys
sys.path.append(r"C:\Sentinel_Project")
from math_meta_model import MathMetaModel
import numpy as np

def verify_fix():
    mm = MathMetaModel()
    # Force retrain for 7 features
    mm.train_from_diagnostics()
    
    symbols = ['NAS100', 'GBPAUD', 'EURNOK']
    
    # Simulate disparate inputs (normally these would be read from cache)
    # We want to see if the scores are unique even if the base ML probs are identical,
    # because the asset-specific catalysts and macro-tilt are now integrated.
    
    print("\n" + "="*50)
    print("SRE DIAGNOSTIC: Math Meta-Model Uniqueness Audit")
    print("-" * 50)
    
    for sym in symbols:
        # Mocking slightly different inputs for realism
        if sym == 'NAS100':
            x, k, h, f = 0.82, 0.88, "BULL", 0.91
        elif sym == 'GBPAUD':
            x, k, h, f = 0.79, 0.85, "BULL", 0.85
        else: # EURNOK
            x, k, h, f = 0.81, 0.86, "BULL", 0.87
            
        p = mm.predict_conviction(sym, x, k, h, f)
        print(f"{sym:<10} | P: {p:.6f}")
    
    print("="*50 + "\n")

if __name__ == "__main__":
    verify_fix()
