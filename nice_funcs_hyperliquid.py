"""
nice_funcs_hyperliquid.py - MASTER UTILITY LAYER (STABLE VERSION)
Fixed SDK spot-meta bugs on Testnet.
"""

import requests
import pandas as pd
import time
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

# HYPERLIQUID_URLS
BASE_URL = "https://api.hyperliquid-testnet.xyz" # TESTNET
INFO_URL = f"{BASE_URL}/info"

def get_exchange_safe(account_obj):
    """Safely initialize Exchange object, catching SDK meta-bugs."""
    try:
        return Exchange(account_obj, BASE_URL)
    except Exception as e:
        print(f"Warning: Exchange SDK init failed (likely spot-meta bug): {e}")
        return None

def ask_bid(symbol: str) -> tuple[float, float]:
    """Returns (ask, bid) from live testnet order book."""
    payload = {"type": "l2Book", "coin": symbol}
    try:
        r = requests.post(INFO_URL, json=payload, timeout=5)
        r.raise_for_status()
        l2 = r.json()["levels"]
        bid = float(l2[0][0]["px"])
        ask = float(l2[1][0]["px"])
        return ask, bid
    except Exception as e:
        print(f"Error fetching ask/bid for {symbol}: {e}")
        return 0.0, 0.0

# Cache for get_sz_px_decimals to prevent caching (0, 0) on network failures
_SZ_PX_DECIMALS_CACHE = {}

def get_sz_px_decimals(symbol: str) -> tuple[int, int]:
    """
    Returns (size_decimals, price_decimals) for valid order sizing.
    ⚡ Bolt Optimization: Cached manually to save ~0.7s per order by skipping
    redundant HTTP calls, while avoiding caching error states like (0, 0).
    """
    if symbol in _SZ_PX_DECIMALS_CACHE:
        return _SZ_PX_DECIMALS_CACHE[symbol]

    try:
        r = requests.post(INFO_URL, json={"type": "meta"}, timeout=5)
        r.raise_for_status()
        meta = r.json()
        sym_info = next((s for s in meta["universe"] if s["name"] == symbol), None)
        if not sym_info:
            return 0, 0
        sz_dec = sym_info["szDecimals"]
        
        # Determine price decimals from a fresh tick
        ask, _ = ask_bid(symbol)
        px_dec = len(str(ask).split(".")[1]) if "." in str(ask) else 0

        # Only cache successful lookups
        result = (sz_dec, px_dec)
        if sz_dec > 0 or px_dec > 0:
            _SZ_PX_DECIMALS_CACHE[symbol] = result
        return result
    except Exception as e:
        print(f"Error fetching decimals for {symbol}: {e}")
        return 0, 0

def get_ohlcv(symbol: str, interval: str, lookback_days: int) -> pd.DataFrame:
    """Fetches candle data from Hyperliquid Testnet API."""
    from datetime import datetime, timedelta
    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": symbol,
            "interval": interval,
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000),
        }
    }
    try:
        r = requests.post(INFO_URL, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df = df[['t', 'o', 'h', 'l', 'c', 'v']]
        df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        cols = ["open", "high", "low", "close", "volume"]
        df[cols] = df[cols].astype(float)
        return df
    except Exception as e:
        print(f"Error fetching OHLCV for {symbol}: {e}")
        return pd.DataFrame()

def get_position(symbol: str, account_address: str) -> dict:
    """Returns current position info for an address on Testnet."""
    try:
        payload = {"type": "clearinghouseState", "user": account_address}
        r = requests.post(INFO_URL, json=payload, timeout=5)
        state = r.json()

        for pos in state.get("assetPositions", []):
            p = pos["position"]
            if p["coin"] == symbol and float(p["szi"]) != 0:
                size = float(p["szi"])
                return {
                    "in_pos": True,
                    "size": size,
                    "long": size > 0,
                    "entry_px": float(p["entryPx"]),
                    "pnl_pct": float(p.get("returnOnEquity", 0)) * 100,
                }
    except Exception as e:
        print(f"Error fetching position for {symbol}: {e}")
    
    return {"in_pos": False, "size": 0, "long": None, "entry_px": 0, "pnl_pct": 0}

def limit_order(coin: str, is_buy: bool, sz: float, limit_px: float,
                reduce_only: bool, account_obj) -> dict:
    """Places a GTC limit order on Testnet."""
    exchange = get_exchange_safe(account_obj)
    if not exchange:
        print("CRITICAL: Cannot place order because SDK setup failed.")
        return {"status": "error", "message": "SDK Init Failed"}
        
    sz_dec, _ = get_sz_px_decimals(coin)
    sz = round(sz, sz_dec)
    try:
        result = exchange.order(
            coin, is_buy, sz, limit_px,
            {"limit": {"tif": "Gtc"}},
            reduce_only=reduce_only
        )
        return result
    except Exception as e:
        print(f"Error placing limit order for {coin}: {e}")
        return {"status": "error", "message": str(e)}

def cancel_all_orders(account_obj):
    """Cancel all open orders on Testnet."""
    exchange = get_exchange_safe(account_obj)
    if not exchange:
        return False
        
    try:
        payload = {"type": "openOrders", "user": account_obj.address}
        r = requests.post(INFO_URL, json=payload, timeout=5)
        open_orders = r.json()
        for order in open_orders:
            exchange.cancel(order["coin"], order["oid"])
        return True
    except Exception as e:
        print(f"Error cancelling orders: {e}")
        return False

def pnl_close(symbol: str, tp_pct: float, sl_pct: float, account_obj):
    """Monitor PnL and close position if TP or SL is hit."""
    pos = get_position(symbol, account_obj.address)
    if not pos["in_pos"]:
        return False
        
    pnl = pos["pnl_pct"]
    if pnl >= tp_pct or pnl <= sl_pct:
        print(f"[EXIT] PnL {pnl:.2f}% hit target ({tp_pct}% / {sl_pct}%). Closing {symbol}.")
        sz = abs(pos["size"])
        ask, bid = ask_bid(symbol)
        is_buy_to_close = not pos["long"]
        close_px = ask if is_buy_to_close else bid
        return limit_order(symbol, is_buy_to_close, sz, close_px, True, account_obj)
    
    return False

def adjust_leverage_usd_size(symbol: str, usd_size: float, leverage: int, account_obj):
    """Sets leverage (isolated) and returns (leverage, crypto_size)."""
    exchange = get_exchange_safe(account_obj)
    try:
        if exchange:
            try:
                exchange.update_leverage(leverage, symbol, is_cross=False)
            except Exception as le:
                print(f"Leverage update skipped/failed (likely already set): {le}")
            
        ask, _ = ask_bid(symbol)
        if ask == 0: return leverage, 0.0
        size = (usd_size / ask) * leverage
        sz_dec, _ = get_sz_px_decimals(symbol)
        return leverage, round(size, sz_dec)
    except Exception as e:
        print(f"Error adjusting leverage for {symbol}: {e}")
        return leverage, 0.0
