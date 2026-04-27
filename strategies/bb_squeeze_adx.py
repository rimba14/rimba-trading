"""
bb_squeeze_adx.py - CORE STRATEGY LOGIC (Portable Version)
Implements Bollinger Band Squeeze + ADX without Ta-Lib dependency.
"""

import pandas as pd
import numpy as np

def calculate_indicators(df: pd.DataFrame, 
                         bb_window=20, bb_std=2.0, 
                         keltner_window=20, keltner_atr_mult=1.5, 
                         adx_period=14):
    """
    Calculates all indicators using pure pandas/numpy.
    """
    if len(df) < max(bb_window, keltner_window, adx_period) + 1:
        return df

    # 1. Bollinger Bands
    df['bb_mid'] = df['close'].rolling(window=bb_window).mean()
    df['bb_std'] = df['close'].rolling(window=bb_window).std()
    df['bb_upper'] = df['bb_mid'] + (bb_std * df['bb_std'])
    df['bb_lower'] = df['bb_mid'] - (bb_std * df['bb_std'])

    # 2. Keltner Channels (using ATR)
    # ATR Calculation
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['tr'] = ranges.max(axis=1)
    df['atr'] = df['tr'].rolling(window=keltner_window).mean()
    
    df['sma'] = df['close'].rolling(window=keltner_window).mean()
    df['kc_upper'] = df['sma'] + (keltner_atr_mult * df['atr'])
    df['kc_lower'] = df['sma'] - (keltner_atr_mult * df['atr'])

    # 3. Squeeze Definition
    df['squeeze_on'] = (df['bb_upper'] < df['kc_upper']) & (df['bb_lower'] > df['kc_lower'])

    # 4. ADX Calculation
    plus_dm = df['high'].diff()
    minus_dm = df['low'].diff()
    
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    minus_dm = minus_dm.abs()
    
    tr_smooth = df['tr'].rolling(window=adx_period).mean()
    plus_di = 100 * (plus_dm.rolling(window=adx_period).mean() / tr_smooth)
    minus_di = 100 * (minus_dm.rolling(window=adx_period).mean() / tr_smooth)
    
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df['adx'] = dx.rolling(window=adx_period).mean()

    return df



def get_signals(df: pd.DataFrame, adx_threshold=25):
    """
    Returns (long_signal: bool, short_signal: bool) for the latest candle.
    """
    if len(df) < 2:
        return False, False

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # Squeeze Release: Squeeze was ON in previous candle, and OFF in current
    squeeze_released = prev['squeeze_on'] and not latest['squeeze_on']
    
    # ADX Confirmation
    strongly_trending = latest['adx'] > adx_threshold

    # Price Breakouts
    long_breakout = latest['close'] > latest['bb_upper']
    short_breakout = latest['close'] < latest['bb_lower']

    long_sig = squeeze_released and strongly_trending and long_breakout
    short_sig = squeeze_released and strongly_trending and short_breakout

    return long_sig, short_sig
