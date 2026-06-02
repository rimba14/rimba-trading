import numpy as np
import pandas as pd
import sys
import os

sys.path.append(r"C:\Sentinel_Project")

def test_spectral_denoiser():
    print("--- Testing Spectral Denoiser ---")
    import gitagent_spectral_denoiser as spec
    
    # Generate synthetic non-uniform data
    t = np.sort(np.random.uniform(0, 100, 100))
    close = 100 + np.cumsum(np.random.normal(0, 1, 100))
    volume = np.random.uniform(10, 100, 100)
    
    df = pd.DataFrame({
        "close": close,
        "tick_volume": volume
    })
    
    spec_denoise, spec_noise = spec.get_spectral_features(df)
    print(f"spec_denoise: {spec_denoise:.4f}, spec_noise: {spec_noise:.4f}")
    assert spec_denoise >= 0.0 and spec_noise >= 0.0
    print("[OK] Spectral Denoiser test passed.")

def test_randomized_krylov_svd():
    print("--- Testing Randomized Krylov SVD ---")
    from alpha_combiner import randomized_krylov_svd
    
    # Create high-dimensional matrix
    A = np.random.normal(size=(50, 50))
    # Low-rank structure
    U_true, S_true, Vt_true = np.linalg.svd(A, full_matrices=False)
    S_true[10:] = 0.0 # Make it rank 10
    A_low_rank = (U_true * S_true) @ Vt_true
    
    U, S, Vt = randomized_krylov_svd(A_low_rank, rank=10)
    print(f"U shape: {U.shape}, S shape: {S.shape}, Vt shape: {Vt.shape}")
    assert U.shape == (50, 10)
    assert S.shape == (10,)
    assert Vt.shape == (10, 50)
    
    # Compute reconstruction error
    A_approx = (U * S) @ Vt
    err = np.linalg.norm(A_low_rank - A_approx)
    print(f"Reconstruction Error: {err:.6f}")
    assert err < 1e-10
    print("[OK] Randomized Krylov SVD test passed.")

def test_hmm_condition_number():
    print("--- Testing HMM Condition Number ---")
    import gitagent_hmm
    
    # Simulate regime behavior
    prices = 100 * np.cumprod(1 + np.random.normal(0.001, 0.01, 150))
    best_label, best_prob, label_probs = gitagent_hmm.get_current_state(prices, lookback=100)
    print(f"HMM Best Label: {best_label} ({best_prob:.4f})")
    print(f"HMM label_probs: {label_probs}")
    
    cond_num = label_probs.get("regime_condition_number")
    print(f"HMM Transition Matrix Condition Number: {cond_num}")
    assert cond_num is not None
    assert cond_num >= 1.0
    print("[OK] HMM Condition Number test passed.")

def test_matrix_integrity_gating():
    print("--- Testing Matrix Integrity Gating ---")
    from monitor_sentinel import verify_regime_matrix_integrity
    from arcticdb import Arctic
    import git_arctic
    
    # Write mock metrics to ArcticDB
    ac = git_arctic.get_arctic()
    lib = ac["oracle_cache"] if "oracle_cache" in ac.list_libraries() else ac.create_library("oracle_cache")
    
    df_metrics_good = pd.DataFrame([{
        "regime_condition_number": 2.5,
        "timestamp": int(time.time())
    }])
    lib.write("TEST_SYMBOL_regime_metrics", df_metrics_good)
    
    from monitor_sentinel import ArcticDBClientWrapper
    db_client = ArcticDBClientWrapper(ac)
    
    # verify_regime_matrix_integrity with low cond_num -> should return True
    good_result = verify_regime_matrix_integrity(db_client, "TEST_SYMBOL")
    print(f"Good Regime Integrity verification: {good_result}")
    assert good_result is True
    
    # Write bad metrics (cond_num > 15.0)
    df_metrics_bad = pd.DataFrame([{
        "regime_condition_number": 18.2,
        "timestamp": int(time.time())
    }])
    lib.write("TEST_SYMBOL_regime_metrics", df_metrics_bad)
    
    # verify_regime_matrix_integrity with high cond_num -> should return False
    ac_bad = Arctic("lmdb://./data/arctic_cache")
    db_client_bad = ArcticDBClientWrapper(ac_bad)
    bad_result = verify_regime_matrix_integrity(db_client_bad, "TEST_SYMBOL")
    print(f"Bad Regime Integrity verification: {bad_result}")
    assert bad_result is False
    
    print("[OK] Matrix Integrity Gating test passed.")

if __name__ == "__main__":
    import time
    test_spectral_denoiser()
    test_randomized_krylov_svd()
    test_hmm_condition_number()
    test_matrix_integrity_gating()
    print("\n[SUCCESS] ALL CCM Quantum-Leap Integration unit tests passed successfully!")
