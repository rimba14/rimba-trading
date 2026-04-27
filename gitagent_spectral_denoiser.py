import numpy as np
import pandas as pd
from scipy.fft import fft, ifft, fftfreq
from typing import Tuple, Dict, Any

class SpectralDenoiser:
    """
    Fourier Trend Reconstruction (Banushev/Rentec style)
    Extracts the clean harmonic trend by keeping top-k frequencies.
    """
    def __init__(self, top_k: int = 5):
        self.top_k = top_k

    def get_denoised_trend(self, prices: np.ndarray) -> np.ndarray:
        N = len(prices)
        if N < 32: return prices
        
        # 1. Detrend to prevent spectral leakage
        x = np.arange(N)
        coeffs = np.polyfit(x, prices, 1)
        linear_trend = np.polyval(coeffs, x)
        detrended = prices - linear_trend
        
        # 2. FFT
        yf = fft(detrended)
        xf = fftfreq(N, 1)
        
        # 3. Keep only top-k harmonics
        indices = np.argsort(np.abs(yf))[-self.top_k:]
        filtered_yf = np.zeros_like(yf)
        filtered_yf[indices] = yf[indices]
        
        # 4. Inverse FFT
        reconstructed = ifft(filtered_yf).real
        return reconstructed + linear_trend

    def audit(self, df: pd.DataFrame) -> Dict[str, Any]:
        if len(df) < 128:
            return {"spec_denoise": 0.0, "residual_noise": 0.0}
            
        prices = df['close'].values[-128:]
        clean_trend = self.get_denoised_trend(prices)
        
        current_price = prices[-1]
        trend_val = clean_trend[-1]
        
        # Normalized residual (Distance from harmonic equilibrium)
        spec_denoise = np.tanh((trend_val - current_price) / (np.std(prices) + 1e-9))
        residual_noise = np.var(prices - clean_trend) / (np.var(prices) + 1e-9)
        
        return {
            "spec_denoise": float(spec_denoise),
            "residual_noise": float(residual_noise)
        }

def get_spectral_features(df: pd.DataFrame) -> Tuple[float, float]:
    sd = SpectralDenoiser()
    res = sd.audit(df)
    return res['spec_denoise'], res['residual_noise']
