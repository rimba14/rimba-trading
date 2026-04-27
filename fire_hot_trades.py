import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import gitagent_synthesis as syn
import gitagent_transformer as trans
import gitagent_microstructure as micro
import gitagent_execute_sor as sor
import json
import os
from datetime import datetime, timezone

# --- SENTINEL HELPER FUNCTIONS (Copy from vantage_execute.py) ---
def rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def macd(series):
    exp1 = series.ewm(span=12, adjust=False).mean()
    exp2 = series.ewm(span=26, adjust=False).mean()
    return exp1 - exp2

def ad_flow(df):
    cl, hi, lo, vol = df['close'], df['high'], df['low'], df['tick_volume']
    mfv = ((cl - lo) - (hi - cl)) / (hi - lo + 1e-9) * vol
    return mfv.rolling(20).mean()

def bollinger_bands(series, period=20, std=2):
    sma = series.rolling(period).mean()
    sd = series.rolling(period).std()
    return sma + (std * sd), sma - (std * sd)

def detect_order_blocks(df):
    if len(df) < 5: return 0
    last, prev = df.iloc[-1], df.iloc[-2]
    if last['close'] > prev['high'] and prev['close'] < prev['open']: return 1
    if last['close'] < prev['low'] and prev['close'] > prev['open']: return -1
    return 0

def calculate_atr(df, period=14):
    tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]

# --- EXECUTION LOGIC ---
if not mt5.initialize():
    print("MT5 Init Failed")
    quit()

targets = ["USDJPY", "USDCAD"]
thesis_file = "C:\\Sentinel_Project\\\position_thesis.json"
POSITION_THESIS = {}
if os.path.exists(thesis_file):
    with open(thesis_file, 'r') as f:
        POSITION_THESIS = json.load(f)

for sym in targets:
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 100)
    if rates is None or len(rates) < 50: continue
    df = pd.DataFrame(rates)
    
    tick = mt5.symbol_info_tick(sym)
    if not tick: continue
    
    # 1. Calculate v10.6 Sentinel Snapshot
    price = tick.ask # Manual BUY
    atr = calculate_atr(df)
    r = rsi(df['close']).iloc[-1]
    
    ub, lb = bollinger_bands(df['close'])
    
    snapshot = {
        "trend": 1 if df['close'].rolling(50).mean().iloc[-1] > df['close'].rolling(200).mean().iloc[-1] else -1,
        "smc": 1 if price > df['close'].rolling(50).mean().iloc[-1] and r < 40 else -1, # Simplification
        "whale": 0.0,
        "macd": 1 if macd(df['close']).iloc[-1] > 0 else -1,
        "ad": 1 if ad_flow(df).iloc[-1] > 0 else -1,
        "bb": 1 if price > ub.iloc[-1] else (-1 if price < lb.iloc[-1] else 0),
        "ob": detect_order_blocks(df),
        "sl_barrier": price - (1.5 * atr),
        "tp_barrier": price + (1.5 * 2.5 * atr),
        "bars_held": 0,
        "entry_score": 30.0 # Force override
    }

    # 2. Fire Trade (Min volume for safety on $500 balance)
    lot = 0.01 
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "magic": 10600,
        "comment": "v10.6 Sentinel Bypass",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    print(f"[BYPASS] Firing {sym} BUY @ {price}...")
    from gitagent_action_layer import get_action_layer
    al = get_action_layer()
    result = al.execute_smart_trade(sym, mt5.ORDER_TYPE_BUY, lot, snapshot['sl_barrier'], snapshot['tp_barrier'], "v10.6 Sentinel Bypass")
    
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        POSITION_THESIS[str(result.order)] = snapshot
        print(f"[SUCCESS] {sym} Executed. Ticket: {result.order}")
    else:
        print(f"[FAIL] {sym} Rejected: {result.comment if result else 'Unknown'}")


# Save updated thesis for the master engine to take over
with open(thesis_file, 'w') as f:
    json.dump(POSITION_THESIS, f, indent=4)

mt5.shutdown()
