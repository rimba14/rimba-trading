import sys
from pathlib import Path
sys.path.append(r"C:\Sentinel_Project")

from math_meta_model import MathMetaModel

def run_test():
    mm = MathMetaModel()
    
    print("\n--- Test 1: Valid Features (predict_conviction) ---")
    res1 = mm.predict_conviction("BTCUSD", {
        "xgb_p": 0.85,
        "kronos_p": 0.85,
        "wasserstein_state": "TRENDING",
        "faiss_sim": 0.9,
        "sentiment_score": 0.8
    })
    print(f"Result (Expected > 0.51): {res1:.4f}")
    
    print("\n--- Test 2: HMM Cold Start (None wasserstein_state) ---")
    res2 = mm.predict_conviction("BTCUSD", {
        "xgb_p": 0.85,
        "kronos_p": 0.85,
        "wasserstein_state": None,
        "faiss_sim": 0.9,
        "sentiment_score": 0.8
    })
    print(f"Result (Expected 0.0): {res2:.4f}")

    print("\n--- Test 3: HMM Cold Start (CLOSED wasserstein_state) ---")
    res3 = mm.predict_conviction("BTCUSD", {
        "xgb_p": 0.85,
        "kronos_p": 0.85,
        "wasserstein_state": "MARKET_CLOSED_OR_STAGNANT",
        "faiss_sim": 0.9,
        "sentiment_score": 0.8
    })
    print(f"Result (Expected 0.0): {res3:.4f}")

    print("\n--- Test 4: FAISS Cold Start (0.0 similarity) ---")
    res4 = mm.predict_conviction("BTCUSD", {
        "xgb_p": 0.85,
        "kronos_p": 0.85,
        "wasserstein_state": "TRENDING",
        "faiss_sim": 0.0,
        "sentiment_score": 0.8
    })
    print(f"Result (Expected 0.0): {res4:.4f}")

    print("\n--- Test 5: get_conviction Valid ---")
    # feature_array: [xgb, kronos, hmm_state, faiss_sim]
    res5 = mm.get_conviction([0.85, 0.85, 1.0, 0.9], "BTCUSD")
    print(f"Result: {res5:.4f}")

    print("\n--- Test 6: get_conviction HMM Cold (0.0) ---")
    res6 = mm.get_conviction([0.85, 0.85, 0.0, 0.9], "BTCUSD")
    print(f"Result (Expected 0.0): {res6:.4f}")

    print("\n--- Test 7: get_conviction FAISS Cold (0.0) ---")
    res7 = mm.get_conviction([0.85, 0.85, 1.0, 0.0], "BTCUSD")
    print(f"Result (Expected 0.0): {res7:.4f}")

if __name__ == "__main__":
    run_test()
