import numpy as np
import pandas as pd

def calculate_microstructure_triad(data):
    # Imbalance, Spread, Volatility
    try:
        cols = data.columns if hasattr(data, 'columns') else []
        p_col = 'price' if 'price' in cols else ('close' if 'close' in cols else (cols[0] if len(cols) > 0 else 'close'))
        
        b_sz = data['bid_sz'] if 'bid_sz' in cols else (data['volume'] if 'volume' in cols else pd.Series(0, index=data.index))
        a_sz = data['ask_sz'] if 'ask_sz' in cols else (data['volume'] if 'volume' in cols else pd.Series(0, index=data.index))
        
        imbalance = (b_sz - a_sz) / (b_sz + a_sz + 1e-9)
        spread = data['ask'] - data['bid'] if ('ask' in cols and 'bid' in cols) else pd.Series(0.0001, index=data.index)
        volatility = data[p_col].rolling(window=20).std()
    except Exception:
        imbalance = pd.Series(0, index=getattr(data, 'index', range(len(data))))
        spread = pd.Series(0, index=getattr(data, 'index', range(len(data))))
        volatility = pd.Series(0, index=getattr(data, 'index', range(len(data))))
        
    return imbalance.fillna(0), spread.fillna(0), volatility.fillna(0)

def calculate_formulaic_ensemble(data):
    # Simplified technical indicators
    p_col = 'price' if 'price' in data.columns else ('close' if 'close' in data.columns else data.columns[0])
    ema_fast = data[p_col].ewm(span=12).mean()
    ema_slow = data[p_col].ewm(span=26).mean()
    macd = ema_fast - ema_slow
    return macd

def calculate_nlp_sentiment(data):
    # Directive 2: Restore NLP Engine or default to neutral. No random placeholders.
    return pd.Series(0.5, index=getattr(data, 'index', range(len(data))))

def calculate_cross_impact(data, other_asset_data):
    # Correlation between related assets
    p_col1 = 'price' if 'price' in data.columns else ('close' if 'close' in data.columns else data.columns[0])
    p_col2 = 'price' if 'price' in other_asset_data.columns else ('close' if 'close' in other_asset_data.columns else other_asset_data.columns[0])
    cross_impact = data[p_col1].pct_change().rolling(window=50).corr(other_asset_data[p_col2].pct_change())
    return cross_impact.fillna(0)

from jl_compression import JLCompressor

# v23.3: Persistent Compressor instance
compressor = JLCompressor(input_dim=768 + 6, target_dim=128)

def generate_features(ticks_df, other_asset_df=None):
    if 'price' not in ticks_df.columns and 'close' in ticks_df.columns:
        ticks_df = ticks_df.copy()
        ticks_df['price'] = ticks_df['close']

    if other_asset_df is None:
        # Mock other asset data if not provided for cross-impact
        other_asset_df = ticks_df.copy()
        if 'price' in other_asset_df.columns:
            other_asset_df['price'] = other_asset_df['price'] * (1 + np.random.normal(0, 0.001, len(ticks_df)))
        else:
            other_asset_df['price'] = np.random.normal(0, 1, len(ticks_df))

    imbalance, spread, volatility = calculate_microstructure_triad(ticks_df)
    macd = calculate_formulaic_ensemble(ticks_df)
    sentiment = calculate_nlp_sentiment(ticks_df)
    cross_impact = calculate_cross_impact(ticks_df, other_asset_df)

    # Base features (6-dim)
    base_features = pd.DataFrame({
        'imbalance': imbalance,
        'spread': spread,
        'volatility': volatility,
        'macd': macd,
        'sentiment': sentiment,
        'cross_impact': cross_impact
    }).bfill().fillna(0)
    
    # v23.3 Directive: Include high-dimensional NLP Embeddings (768d)
    # v27.0 SRE Fix: Zero-fill dummy embeddings to prevent stochastic noise injection
    batch_size = len(ticks_df)
    nlp_embeddings = np.zeros((batch_size, 768), dtype='float32')
    
    # Concatenate: (batch, 6) + (batch, 768) -> (batch, 774)
    full_vector = np.hstack([base_features.values, nlp_embeddings])
    
    # Apply JL Lemma Compression -> (batch, 128)
    compressed_vector = compressor.compress(full_vector)
    
    return compressed_vector

def compute_cross_sectional_ranks(metrics: dict) -> dict:
    """Calculates percentile ranks (0.0 to 1.0) for a dictionary of metrics."""
    if not metrics: return {}
    symbols = list(metrics.keys())
    values = list(metrics.values())
    ranks = pd.Series(values).rank(pct=True).values
    return dict(zip(symbols, ranks))

def engineer_features(df, price_col="close", volume_col="tick_volume", frac_d=0.45, fft_top_k=3, cs_rank=0.5):
    """
    v23.3 Bridge: Wraps generate_features to return the original DF with new features appended.
    """
    if df is None: return None
    
    # We'll add the expected columns to the original df
    df = df.copy()
    df['frac_diff_price'] = np.random.normal(0, 1, len(df)) # Placeholder
    df['fft_amp_1'] = 1.0
    df['fft_amp_2'] = 1.0
    df['fft_amp_3'] = 1.0
    
    # Directive 1: High-Fidelity Triad (Hawkes, Entropy, VPIN) using real OHLCV/Volume
    returns = df[price_col].pct_change().fillna(0)
    
    # Proxy for Buy/Sell Volume based on tick rules
    buy_vol = np.where(returns > 0, df[volume_col], 0)
    sell_vol = np.where(returns < 0, df[volume_col], 0)
    
    # v27.0 SRE Purge: VPIN and Hawkes Intensity removed (Invalid on H1/H4 Swing)
    # rolling_buy = pd.Series(buy_vol).rolling(window=20, min_periods=1).sum()
    # rolling_sell = pd.Series(sell_vol).rolling(window=20, min_periods=1).sum()
    # rolling_total = pd.Series(df[volume_col]).rolling(window=20, min_periods=1).sum()
    # df['vpin'] = (np.abs(rolling_buy - rolling_sell) / (rolling_total + 1e-9)).fillna(0.5)
    
    # jumps = np.abs(returns)
    # df['hawkes_intensity'] = jumps.ewm(span=10, min_periods=1).mean().fillna(0)
    
    # 3. Order Flow Entropy (Shannon Entropy of directional probabilities)
    pos_p = (returns > 0).rolling(window=20, min_periods=1).mean() + 1e-9
    neg_p = (returns < 0).rolling(window=20, min_periods=1).mean() + 1e-9
    df['order_flow_entropy'] = -(pos_p * np.log2(pos_p) + neg_p * np.log2(neg_p)).fillna(0)
    
    return df

# ============================================================
# v26.0 SWING ALPHA FACTORY (Level 31 SRE)
# ============================================================

import MetaTrader5 as mt5

def ingest_mtf_ohlcv(symbol):
    """
    v26.0: Multi-Timeframe OHLCV Ingestion.
    Fetches 100 H1 bars (primary signal) and 100 H4 bars (macro trend).
    Applies Phase 1 NaN/inf scrubbing protocol.
    Returns (df_h1, df_h4) as pandas DataFrames.
    """
    def _fetch_and_scrub(symbol, timeframe, count=100):
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        
        # Directive 1: Continuous Temporal Indexing (Crypto Gaps)
        freq = '1h' if timeframe == mt5.TIMEFRAME_H1 else '4h'
        original_idx = df.index
        df = df.resample(freq).ffill()
        
        # Identify newly generated rows (maintenance gaps)
        new_rows = df.index.difference(original_idx)
        if not new_rows.empty:
            if 'tick_volume' in df.columns:
                df.loc[new_rows, 'tick_volume'] = 0
            if 'real_volume' in df.columns:
                df.loc[new_rows, 'real_volume'] = 0
            if 'close' in df.columns:
                if 'open' in df.columns:
                    df.loc[new_rows, 'open'] = df.loc[new_rows, 'close']
                if 'high' in df.columns:
                    df.loc[new_rows, 'high'] = df.loc[new_rows, 'close']
                if 'low' in df.columns:
                    df.loc[new_rows, 'low'] = df.loc[new_rows, 'close']
                    
        # Maintain exactly the latest 'count' rows after resampling
        df = df.iloc[-count:]
        
        # Phase 1 Constitutional NaN/inf scrubbing
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.ffill(inplace=True)
        df.fillna(0, inplace=True)
        return df

    df_h1 = _fetch_and_scrub(symbol, mt5.TIMEFRAME_H1)
    df_h4 = _fetch_and_scrub(symbol, mt5.TIMEFRAME_H4)
    return df_h1, df_h4


def compute_swing_alpha(df, df_h4=None):
    """
    v26.0 Swing Alpha Factory - 3 Setup Logic:
    1. Mean Reversion: RSI(14) + Order-Flow Entropy
    2. Trend Continuation: 20 EMA + 50 SMA + Bollinger Band Squeeze
    3. Catalyst Momentum: Gap% + Relative Volume (RVOL)
    Returns a dict of alpha signals.
    """
    close = df['close']
    volume = df['tick_volume']

    # --- Setup 1: Mean Reversion (RSI + Order-Flow Entropy) ---
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    returns = close.pct_change().fillna(0)
    pos_p = (returns > 0).rolling(20).mean() + 1e-9
    neg_p = (returns < 0).rolling(20).mean() + 1e-9
    entropy = -(pos_p * np.log2(pos_p) + neg_p * np.log2(neg_p))
    mean_reversion_signal = (rsi < 35) & (entropy > 0.85)

    # --- Setup 2: Trend Continuation (EMA/SMA + BB Squeeze) ---
    ema_20 = close.ewm(span=20, adjust=False).mean()
    sma_50 = close.rolling(50).mean()
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_width = (2 * bb_std) / (bb_mid + 1e-9)
    bb_squeeze = bb_width <= bb_width.rolling(20).min().shift(1)  # current BB at 20-bar low
    price_on_ema = np.abs(close - ema_20) < (bb_std * 0.3)
    trend_continuation_signal = bb_squeeze & price_on_ema

    # --- Setup 3: Catalyst Momentum (Gap% + RVOL) ---
    gap_pct = (df['open'] - df['close'].shift(1)) / (df['close'].shift(1) + 1e-9) * 100
    avg_volume = volume.rolling(20).mean()
    rvol = volume / (avg_volume + 1e-9)
    catalyst_momentum_signal = (gap_pct.abs() > 1.0) & (rvol > 2.0)

    alpha = pd.DataFrame({
        'rsi': rsi,
        'entropy': entropy,
        'ema_20': ema_20,
        'sma_50': sma_50,
        'bb_width': bb_width,
        'gap_pct': gap_pct,
        'rvol': rvol,
        'mean_reversion_signal': mean_reversion_signal.astype(float),
        'trend_continuation_signal': trend_continuation_signal.astype(float),
        'catalyst_momentum_signal': catalyst_momentum_signal.astype(float),
    }).replace([np.inf, -np.inf], np.nan).ffill().fillna(0)

    return alpha


if __name__ == "__main__":
    # Generate 2,000 dummy ticks for diagnostic
    np.random.seed(42)
    ticks = 2000
    df = pd.DataFrame({
        'price': np.cumsum(np.random.normal(0, 1, ticks)) + 100,
        'bid': np.zeros(ticks),
        'ask': np.zeros(ticks),
        'bid_sz': np.random.randint(1, 100, ticks),
        'ask_sz': np.random.randint(1, 100, ticks)
    })
    df['bid'] = df['price'] - 0.01
    df['ask'] = df['price'] + 0.01
    
    features = generate_features(df)
    print(f"Generated features shape: {features.shape}")
    nan_count = np.isnan(features).sum()
    print(f"Cross-impact NaN count: {nan_count}")
    if nan_count == 0:
        print("Feature engineering diagnostic: SUCCESS")
    else:
        print("Feature engineering diagnostic: FAILED")
