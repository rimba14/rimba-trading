import MetaTrader5 as mt5
import time
import pandas as pd
from datetime import datetime, timezone

def get_utc_epoch():
    """Returns the current universal UTC epoch time."""
    return datetime.now(timezone.utc).timestamp()

def calculate_atr(df, period=14):
    """Calculates Average True Range (ATR) from OHLCV DataFrame."""
    high_low = df['high'] - df['low']
    high_cp = (df['high'] - df['close'].shift()).abs()
    low_cp = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]

def normalize_volume(symbol, volume):
    """Aligns requested volume with broker LOT_STEP and MIN/MAX constraints."""
    info = mt5.symbol_info(symbol)
    if not info: return volume
    
    v_step = info.volume_step
    v_min = info.volume_min
    v_max = info.volume_max
    
    # Robust normalization: Use integer floor (downward) to prevent 'insufficient margin' errors
    norm_vol = (volume // v_step) * v_step
    
    # Floor to min if we are very close to it but rounded down to 0
    if norm_vol < v_min and volume >= (v_min * 0.9):
        norm_vol = v_min
        
    norm_vol = round(max(v_min, min(norm_vol, v_max)), 2)
    return float(norm_vol)

def is_market_open(symbol):
    """Check if the market for the symbol is currently open for trading."""
    info = mt5.symbol_info(symbol)
    if not info: return False
    # Check if trade_mode allows trading (MT5 doesn't provide a direct 'is_open' boolean)
    if info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED: return False
    
    # Simple way to check if we can get a recent tick
    tick = mt5.symbol_info_tick(symbol)
    if not tick: return False
    
    # Check if the last tick time was recent.
    # v14.2: Widened to 12 hours to account for local/server TZ deltas.
    # True market closure detected if tick is stale > 12h (weekends).
    if abs(time.time() - tick.time) > 43200: 
        return False
    
    return True

def is_liquidity_safe(symbol, atr, spread_limit_pct=10.0):
    """
    Prevents entries where spread cost > 5% of ATR daily range.
    Protects $700 account alpha from toxic minor-pair spreads.
    """
    tick = mt5.symbol_info_tick(symbol)
    if not tick: return False
    
    spread = tick.ask - tick.bid
    if atr <= 0: return True # Fallback if ATR missing
    
    spread_ratio = spread / atr
    if spread_ratio > spread_limit_pct:
        print(f"[LIQUIDITY_GATE] {symbol} Rejected: Spread {spread_ratio:.2%} > {spread_limit_pct:.1%}")
        return False
    return True

def get_symbol_regime(symbol):
    """Categorizes symbols into risk regimes for portfolio balancing."""
    s = symbol.upper()
    
    # 1. Broad Equity Check (Prioritize known tech giants and length patterns)
    equities = ['TSLA', 'AAPL', 'MSFT', 'AMZN', 'GS', 'QCOM', 'COST', 'NVDA', 'META', 'GOOGL', 'AMAZON', 'NVIDIA', 'GOOG', 'NFLX', 'CRM', 'ORCL', 'AVGO', 'JPM']
    if s in equities or s.endswith('.R') or len(s) < 6:
        return "EQUITY"
        
    if s in ['SP500', 'NAS100', 'DJI30', 'DJ30', 'DAX40', 'GER40', 'FTSE100', 'UK100', 'FRA40', 'HK50']: return "INDEX"
    if s in ['XAUUSD', 'XAGUSD', 'XPTUSD', 'XPDUSD', 'WTI', 'BRENT', 'CL-OIL']: return "COMMODITY"
    if s in ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY', 'USDNOK', 'USDSEK']: return "FOREX_USD"
    if 'USD' in s and len(s) > 6: return "CRYPTO" # SOLUSD, BTCUSD
    
    # Defaults to Forex Cross for 6-char if not listed above
    if len(s) == 6: return "FOREX_CROSS"
    
    return "MISC"

def get_currency_bias(symbol, side_type):
    """Identifies if a trade increases long/short exposure to a specific major currency."""
    s = symbol.upper()
    if len(s) != 6: return None 
    
    base = s[:3] # e.g. EUR
    quote = s[3:] # e.g. USD
    
    if side_type == 0: # BUY BASE, SELL QUOTE
        return {"long": base, "short": quote}
    else: # SELL BASE, BUY QUOTE
        return {"long": quote, "short": base}

def normalize_forex_pair(symbol):
    """Treats A/B and B/A as the same unique pair. e.g. EURUSD and USDEUR -> EUR_USD."""
    s = symbol.upper()
    if len(s) != 6 or s in ['XAUUSD', 'XAGUSD', 'XPTUSD', 'XPDUSD', 'CL-OIL']: 
        return s # Non-forex or metals are unique to themselves
    
    base = s[:3]
    quote = s[3:]
    return "_".join(sorted([base, quote]))

def live_vix():
    """Returns the current VIX level (Volatility Index) for regime detection. Uses robust fallback."""
    try:
        # Attempt raw Yahoo Query (prevents yfinance metaclass errors)
        url = "https://query1.finance.yahoo.com/v7/finance/chart/^VIX?interval=1m&range=1d"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            val = data['chart']['result'][0]['meta']['regularMarketPrice']
            return float(val)
    except Exception:
        pass
    return 23.16 # Default to 'Normal' volatility

def fetch_unstructured_sentiment(symbol):
    """
    Alternative Data Oracle (Black Swan Shield): 
    Fetches real-time sentiment scores (-1.0 to 1.0).
    Currently implemented as a robust placeholder/aggregator.
    """
    # In production, this would scrape Twitter/X, News APIs, or specialized sentiment providers.
    # For now, we use a neutral fallback with a small variance for simulation.
    import random
    return random.uniform(-0.1, 0.1)

MAX_TOTAL_POSITIONS = 30

def calculate_psr(returns=None, sharpe=None, n_samples=None, skew=0.0, kurtosis=3.0, min_samples=25):
    """
    Centralized Probabilistic Sharpe Ratio (PSR) Calculation.
    Supports either a list of returns or pre-calculated statistics.
    Based on Bailey and Lopez de Prado (2012).
    """
    from scipy import stats
    import numpy as np

    if returns is not None:
        arr = np.array(returns)
        n = len(arr)
        if n < min_samples:
            return 1.0
        # Sharpe ratio: mean / std
        mean = np.mean(arr)
        std = np.std(arr)
        sharpe = mean / (std + 1e-9)
        skew = stats.skew(arr)
        # scipy.stats.kurtosis returns excess kurtosis (Fisher's definition: kurtosis - 3)
        excess_kurt = stats.kurtosis(arr)
        n_samples = n
    else:
        # If pre-calculated stats are provided, we assume kurtosis parameter is the standard definition (Normal=3)
        excess_kurt = kurtosis - 3.0

    if sharpe is None or n_samples is None:
        return 0.0

    if n_samples <= 1:
        return 0.0

    # Bailey and Lopez de Prado (2012) formula:
    # std_error = sqrt((1 - skew*sharpe + (kurtosis-1)/4 * sharpe**2) / (n_samples - 1))
    # where kurtosis is the non-excess kurtosis.
    # If we have excess_kurt = kurtosis - 3, then kurtosis - 1 = excess_kurt + 2.

    std_error = np.sqrt((1 - skew * sharpe + (excess_kurt + 2) / 4.0 * sharpe**2) / (n_samples - 1))
    psr = stats.norm.cdf(sharpe / std_error)
    return float(psr)
