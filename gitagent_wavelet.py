import pywt
import numpy as np
import pandas as pd

def denoise_signal(data, wavelet='db4', level=1):
    """
    Discrete Wavelet Transform (DWT) Denoising via Soft Thresholding.
    Optimized for zero look-ahead bias (rolling context only).
    """
    if len(data) < 2**level: return data
    
    coeffs = pywt.wavedec(data, wavelet, mode='per')
    
    # Calculate universal threshold: sigma * sqrt(2 * log(n))
    # Approximation of sigma using Median Absolute Deviation (MAD) of finest details
    sigma = (1/0.6745) * np.median(np.abs(coeffs[-1] - np.median(coeffs[-1])))
    threshold = sigma * np.sqrt(2 * np.log(len(data)))
    
    # Apply soft thresholding to all detail coefficients
    new_coeffs = [coeffs[0]] # Keep approximations as is
    for i in range(1, len(coeffs)):
        new_coeffs.append(pywt.threshold(coeffs[i], threshold, mode='soft'))
        
    return pywt.waverec(new_coeffs, wavelet, mode='per')[:len(data)]

def extract_mra_features(data, levels=4, wavelet='db4'):
    """
    Multi-Resolution Analysis (MRA): Returns approximation and detail coefficients.
    """
    try:
        coeffs = pywt.wavedec(data, wavelet, level=levels, mode='per')
        # coeffs[0] = approximation (trend)
        # coeffs[1:] = details (volatility/micro-noise at different scales)
        
        features = {}
        features['wave_approx'] = np.mean(coeffs[0])
        for i in range(1, len(coeffs)):
            features[f'wave_detail_L{i}'] = np.mean(coeffs[i])
            features[f'wave_std_L{i}'] = np.std(coeffs[i])
            
        return features
    except:
        return {}

def get_cwt_regime(data, scales=np.arange(1, 32), wavelet='morl'):
    """
    Continuous Wavelet Transform (CWT) Scalogram Analysis.
    Returns: DomScale, Power, and RegimeShift flag.
    """
    if len(data) < 64: return 1.0, 0.0, False
    
    # Compute CWT
    coef, freqs = pywt.cwt(data, scales, wavelet)
    
    # Time-Frequency Scalogram Power
    power = (np.abs(coef)) ** 2
    
    # Global Wavelet Power Spectrum (total power per scale over time)
    gwps = np.mean(power, axis=1)
    
    # Find dominant scale
    dom_idx = np.argmax(gwps)
    dom_scale = scales[dom_idx]
    max_power = gwps[dom_idx]
    
    # Drastic Shift Detection (comparing last 10% vs first 90% of window)
    split = int(0.9 * power.shape[1])
    p_early = np.mean(power[:, :split], axis=1)
    p_late = np.mean(power[:, split:], axis=1)
    
    shift_score = np.sum(np.abs(p_late - p_early)) / (np.sum(p_early) + 1e-9)
    regime_shift = bool(shift_score > 1.5) # Drastic power distribution shift
    
    return float(dom_scale), float(max_power), regime_shift

def wavelet_peak_periods(data, top_k=3, scales=np.arange(2, 64)):
    """
    Wavelet-based period detection for TimesNet integration.
    Identifies scales with highest energy density.
    """
    if len(data) < 64: return [1]*top_k, [0]*top_k
    
    coef, _ = pywt.cwt(data, scales, 'morl')
    power = np.mean((np.abs(coef))**2, axis=1)
    
    # Find local peaks in power spectrum
    peaks = []
    for i in range(1, len(power)-1):
        if power[i] > power[i-1] and power[i] > power[i+1]:
            peaks.append((scales[i], power[i]))
            
    # Sort and take top-k
    peaks.sort(key=lambda x: x[1], reverse=True)
    
    periods = [int(p[0]) for p in peaks[:top_k]]
    amps = [float(p[1]) for p in peaks[:top_k]]
    
    # Fill if not enough peaks found
    while len(periods) < top_k:
        periods.append(1)
        amps.append(0.0)
        
    return periods, amps
