import numpy as np
import pandas as pd

try:
    import finufft
    HAS_FINUFFT = True
except ImportError:
    HAS_FINUFFT = False

def extract_non_uniform_fingerprint(timestamps: np.ndarray, imbalances: np.ndarray, n_modes: int = 32) -> np.ndarray:
    """
    Computes spectral decompositions directly from non-uniform tick intervals 
    to preserve fine market microstructure patterns.
    """
    if len(timestamps) < n_modes:
        return np.zeros(n_modes, dtype=np.complex128)
    
    # Shift and normalize coordinates to [-pi, pi] for FINUFFT compliance
    t_min, t_max = timestamps[0], timestamps[-1]
    if t_max == t_min:
        return np.zeros(n_modes, dtype=np.complex128)
    
    normalized_t = -np.pi + 2 * np.pi * (timestamps - t_min) / (t_max - t_min)
    
    if HAS_FINUFFT:
        try:
            # Execute Type-1 NUFFT directly on irregularly spaced microstructure ticks
            out = finufft.nufft1d1(normalized_t, imbalances.astype(np.complex128), n_modes)
            return out
        except Exception:
            # Safe internal fallback if C++ library errors out at runtime
            pass
            
    # Strict fallback protocol to maintain zero-downtime execution
    uniform_t = np.linspace(-np.pi, np.pi, len(timestamps))
    interp_imbalances = np.interp(uniform_t, normalized_t, imbalances)
    return np.fft.fft(interp_imbalances, n_modes)

def get_spectral_features(ohlcv_df: pd.DataFrame) -> tuple:
    """
    Interface called by Representative Layer in gitagent_synthesis.py.
    Computes spec_denoise and spec_noise features using non-uniform Fourier transforms.
    """
    if ohlcv_df is None or len(ohlcv_df) < 10:
        return 0.0, 0.0
    
    try:
        if isinstance(ohlcv_df.index, pd.DatetimeIndex):
            timestamps = ohlcv_df.index.astype(np.int64) // 10**9
        elif 'timestamp' in ohlcv_df.columns:
            timestamps = ohlcv_df['timestamp'].values
        else:
            timestamps = np.arange(len(ohlcv_df))
        
        close = ohlcv_df['close'].values
        if 'imbalance' in ohlcv_df.columns:
            imbalances = ohlcv_df['imbalance'].values
        elif 'volume_imbalance' in ohlcv_df.columns:
            imbalances = ohlcv_df['volume_imbalance'].values
        else:
            volume = ohlcv_df['tick_volume'].values if 'tick_volume' in ohlcv_df.columns else (ohlcv_df['volume'].values if 'volume' in ohlcv_df.columns else np.ones(len(ohlcv_df)))
            ret = np.diff(close, prepend=close[0])
            imbalances = np.sign(ret) * volume
            
        fingerprint = extract_non_uniform_fingerprint(timestamps, imbalances, n_modes=32)
        amps = np.abs(fingerprint)
        
        # Denoise component: sum of low frequency/dominant amplitudes
        spec_denoise = float(np.sum(amps[:8]))
        # Noise component: sum of high frequency amplitudes
        spec_noise = float(np.sum(amps[8:]))
        
        return spec_denoise, spec_noise
    except Exception:
        return 0.0, 0.0
