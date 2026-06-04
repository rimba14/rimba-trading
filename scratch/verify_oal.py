import numpy as np
import pandas as pd
import sys

sys.path.append(r"C:\Sentinel_Project")

def test_pair_evaluation():
    print("--- Testing Algebraic Pair Evaluation ---")
    from vectorbt_researcher_mcp import evaluate_cross_sectional_pairs
    
    # Generate mock price dataframe (T=100, Assets=5)
    np.random.seed(42)
    prices = 100 * np.cumprod(1 + np.random.normal(0, 0.01, size=(100, 5)), axis=0)
    prices_df = pd.DataFrame(prices, columns=['A', 'B', 'C', 'D', 'E'])
    
    result = evaluate_cross_sectional_pairs(prices_df)
    print(f"Evaluation result: {result}")
    assert result["status"] == "success"
    assert len(result["pairs"]) > 0
    print("[OK] Algebraic Pair Evaluation passed.")

def test_timesnet_prime_alignment():
    print("--- Testing TimesNet Prime Alignment ---")
    import torch
    import gitagent_timesnet as tnet
    
    # Verify nearest prime function
    p1 = tnet.get_nearest_prime(4)
    print(f"Nearest prime to 4: {p1}")
    assert p1 == 5
    
    p2 = tnet.get_nearest_prime(9)
    print(f"Nearest prime to 9: {p2}")
    assert p2 == 11
    
    # Initialize TimesBlock
    block = tnet.TimesBlock(d_model=32, top_k=3, seq_len=128)
    # Synthetic batch of size 1, sequence length 128, channels 32
    x = torch.randn(1, 128, 32)
    out = block(x)
    print(f"Input shape: {x.shape} -> Output shape: {out.shape}")
    assert out.shape == x.shape
    print("[OK] TimesNet Prime Alignment passed.")

if __name__ == "__main__":
    test_pair_evaluation()
    test_timesnet_prime_alignment()
    print("\n[SUCCESS] ALL Operation Algebraic Lattice unit tests passed successfully!")
