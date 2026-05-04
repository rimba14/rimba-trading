import numpy as np
import scipy.stats as stats
from scipy.fft import fft, fftfreq
from gitagent_base import BaseModule
import pandas as pd
import time
from typing import Dict, Any
import MetaTrader5 as mt5

def strict_normalize(series: np.ndarray) -> np.ndarray:
    """
    v19.1 Directive: Strict Input Normalization.
    Transforms raw input into bounded range [-5.0, +5.0] to prevent fixed-point clipping.
    Uses Z-score normalization followed by hard clipping.
    """
    if len(series) < 2: return series
    mean = np.mean(series)
    std = np.std(series) + 1e-9
    norm = (series - mean) / std
    return np.clip(norm, -5.0, 5.0)

def get_m15_dataframe(symbol, count=200):
    """Utility to fetch MT5 M15 rates and return a cleaned DataFrame."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, count)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

class PerceptionLayer(BaseModule):
    """
    Sentinel Perception Layer (Layer 1)
    Responsibility: DWT Denoising -> FFT Period Detection.
    No future leakage.
    """
    def __init__(self):
        super().__init__("Perception")

    def validate_input(self, df: pd.DataFrame) -> bool:
        if df is None or len(df) < 32:
            return False
        return True

    def process(self, ohlcv_df: pd.DataFrame) -> Dict[str, Any]:
        if not self.validate_input(ohlcv_df):
            return {"status": "error", "message": "insufficient_data"}
        
        # Look-ahead Guard: Use only completed bars
        clean_df = ohlcv_df.iloc[:-1] if len(ohlcv_df) > 32 else ohlcv_df
        prices = clean_df['close'].values

        # 1. DWT Denoising
        dwt_results = haar_dwt(prices)
        
        # 2. FFT Period Detection
        fft_results = fft_cycle_detector(prices)
        
        # 3. Kalman Trend
        kalman_results = adaptive_kalman(prices)

        return {
            "dwt": dwt_results,
            "fft": fft_results,
            "kalman": kalman_results,
            "ohlcv_df": clean_df, # Pass-through for RepresentationLayer
            "timestamp": time.time()
        }

def fft_cycle_detector(prices):
    N = len(prices)
    if N < 16:
        return {"period": 0, "phase": 0, "power": 0, "phase_label": "INSUFFICIENT DATA", "cycle_bias": 0}

    x = np.arange(N)
    slope, intercept, _, _, _ = stats.linregress(x, prices)
    detrended = prices - (slope * x + intercept)
    windowed = detrended * np.hanning(N)

    yf = fft(windowed)
    xf = fftfreq(N, 1)[:N//2]
    power = np.abs(yf[:N//2])**2 / (N**2)

    mask = (xf >= 1/40) & (xf <= 1/5)
    if not np.any(mask):
        return {"period": 0, "phase": 0, "power": 0, "phase_label": "NO CYCLE", "cycle_bias": 0}

    filtered_xf = xf[mask]
    filtered_power = power[mask]
    
    idx = np.argmax(filtered_power)
    dom_freq = filtered_xf[idx]
    dom_power = filtered_power[idx]
    dom_period = 1 / dom_freq
    
    start_idx = np.where(mask)[0][0]
    angle = np.angle(yf[idx + start_idx])
    current_phase = (2 * np.pi * dom_freq * (N-1) + angle) % (2 * np.pi)
    
    normalized_phase = float(current_phase / (2 * np.pi))
    cycle_bias = float(np.cos(current_phase))

    if normalized_phase < 0.125 or normalized_phase >= 0.875:
        label = "TROUGH"
    elif normalized_phase < 0.375:
        label = "RISING"
    elif normalized_phase < 0.625:
        label = "PEAK"
    else:
        label = "FALLING"

    return {
        "period": round(float(dom_period), 1),
        "phase": round(normalized_phase, 3),
        "power": float(dom_power),
        "dominance": round(float(dom_power / (np.sum(power) + 1e-9)), 2),
        "phase_label": label,
        "cycle_bias": round(cycle_bias, 3)
    }

def adaptive_kalman(prices):
    N = len(prices)
    if N < 5:
        return {"price": float(prices[-1]), "velocity": 0.0, "noise": 0.01, "innovation": 0.0}

    x = np.array([prices[0], 0.0])
    P = np.eye(2)
    F = np.array([[1, 1], [0, 1]])
    H = np.array([1, 0])
    R = 0.5
    Q = np.array([[0.01, 0], [0, 0.001]])
    innovations = []
    
    for i in range(1, N):
        x_pred = F @ x
        q_scale = 1.0
        if len(innovations) > 3:
            recent_innov_var = np.var(innovations[-5:])
            q_scale = max(1.0, float(recent_innov_var / max(0.01, R)))
        
        P_pred = F @ P @ F.T + Q * q_scale
        z = prices[i]
        y = float(z - H @ x_pred)
        innovations.append(y)
        
        S = float(H @ P_pred @ H.T + R)
        if len(innovations) > 5:
            R = R * 0.9 + 0.1 * max(0.01, float(np.var(innovations[-10:]) - (H @ P_pred @ H.T)))
            R = max(0.01, R)
            
        K = P_pred @ H.T / S
        x = x_pred + K * y
        P = (np.eye(2) - np.outer(K, H)) @ P_pred

    return {
        "price": round(float(x[0]), 2),
        "velocity": round(float(x[1]), 4),
        "noise": round(float(R), 5),
        "innovation": round(float(innovations[-1]), 2) if innovations else 0.0
    }

def haar_dwt(prices):
    N = len(prices)
    if N < 8:
        return {"alignment": 0.0, "trend_dir": 0}

    pow2 = 2**int(np.ceil(np.log2(N)))
    padded = np.pad(prices, (0, pow2 - N), 'edge')
    
    current = padded
    details = []
    approxs = []
    
    for level in range(3):
        approx = (current[0::2] + current[1::2]) / np.sqrt(2)
        detail = (current[0::2] - current[1::2]) / np.sqrt(2)
        details.append(detail)
        approxs.append(approx)
        current = approx

    dirs = []
    for d in details:
        avg = np.mean(d[-max(2, len(d)//4):])
        dirs.append(1 if avg > 0 else -1 if avg < 0 else 0)
    
    deep_approx = approxs[-1]
    trend_dir = 1 if deep_approx[-1] > deep_approx[-2] else -1
    dirs.append(trend_dir)
    alignment = sum(dirs) / len(dirs)
    
    return {
        "alignment": round(float(alignment), 3),
        "trend_dir": int(trend_dir),
        "noise_ratio": round(float(np.var(details[0]) / (np.var(padded) + 1e-6)), 2)
    }

def get_feature_vector_native(symbol: str) -> np.ndarray:
    """
    v11.0: Zero-latency feature vector extraction.
    Constructs a 93-dim state vector for Episodic Memory retrieval.
    """
    # 1. Fetch live ticks (Native)
    tick = mt5.symbol_info_tick(symbol)
    if not tick: return np.zeros(93).astype('float32')
    
    # 2. Construct 93-dim vector
    # We use price, volume, and basic indicators (93 slots)
    # This is a simplified version for Phase 11.0
    vec = np.zeros(93).astype('float32')
    vec[0] = float(tick.bid)
    vec[1] = float(tick.ask)
    vec[2] = float(tick.last)
    vec[3] = float(tick.volume)
    
    # 4-30: Historical Price Drift
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 26)
    if rates is not None:
        closes = [r['close'] for r in rates]
        for i, c in enumerate(closes):
            vec[4+i] = float(c)
            
    # 30-60: Relative Strength / Volatility
    # 60-93: Reserved for HMM/Kronos bits (Injected later if needed)
    
    return vec

def get_feature_vector(symbol: str) -> np.ndarray:
    """Legacy wrapper for backward compatibility."""
    return get_feature_vector_native(symbol)

def information_bottleneck(agent_votes):
    """Placeholder to resolve IndentationError."""
    return {"multiplier": 1.0}
