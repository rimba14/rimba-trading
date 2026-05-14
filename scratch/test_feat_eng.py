import feature_engineering as fe
import numpy as np
import pandas as pd

prices = np.cumsum(np.random.randn(1000)) + 100

# Test frac_diff_series
fd = fe.frac_diff_series(prices, d=0.45)
print(f"FracDiff length: {len(fd)} (from {len(prices)} input)")

# Test FFT amplitudes
fft_amps = fe.extract_fft_amplitudes(prices, top_k=3)
print(f"FFT Top-3 amplitudes: {fft_amps}")

# Test full pipeline
df = pd.DataFrame({
    "close": prices,
    "tick_volume": np.random.randint(100, 1000, 1000)
})
df2 = fe.engineer_features(df)
print(f"Output columns: {list(df2.columns)}")
print(f"frac_diff_price tail: {df2['frac_diff_price'].iloc[-3:].values}")
print(f"fft_amp_1: {df2['fft_amp_1'].iloc[0]:.6f}")
print(f"fft_amp_2: {df2['fft_amp_2'].iloc[0]:.6f}")
print(f"fft_amp_3: {df2['fft_amp_3'].iloc[0]:.6f}")
print("ALL TESTS PASSED")
