import MetaTrader5 as mt5
import json
import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone

THESIS_FILE = "C:\\Sentinel_Project\\position_thesis.json"
METAL_SYMBOLS = ["XAUUSD", "XAGUSD", "GOLD", "SILVER", "XPTUSD", "XPDUSD"]

def calculate_atr(df, period=14):
    if df is None or len(df) < period + 1: return 0.0010
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(period).mean().iloc[-1]

def sync_server_sl_tp(pos, sl, tp):
    info = mt5.symbol_info(pos.symbol)
    if not info: return False
    
    tick_size = info.trade_tick_size
    s_sl = round(sl / tick_size) * tick_size
    s_tp = round(tp / tick_size) * tick_size
    
    # Check if update is actually needed
    if abs(pos.sl - s_sl) < (tick_size / 2) and abs(pos.tp - s_tp) < (tick_size / 2):
        return True
        
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": pos.ticket,
        "sl": float(s_sl),
        "tp": float(s_tp),
        "magic": 123456
    }
    res = mt5.order_send(request)
    return res and res.retcode == mt5.TRADE_RETCODE_DONE

def main():
    if not mt5.initialize():
        print("[FAIL] MT5 Initialization Failed")
        return

    print("--- MASS RE-ANCHORING UTILITY v142 ---")
    
    if os.path.exists(THESIS_FILE):
        with open(THESIS_FILE, 'r') as f:
            thesis_store = json.load(f)
    else:
        thesis_store = {}

    positions = mt5.positions_get()
    if not positions:
        print("[INFO] No open positions found.")
        mt5.shutdown()
        return

    updated_count = 0
    for p in positions:
        sym = p.symbol
        is_buy = (p.type == mt5.ORDER_TYPE_BUY)
        
        # 1. Fetch Fresh ATR
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 100)
        if rates is None:
            print(f"[SKIP] {sym} Could not fetch ATR")
            continue
        
        df = pd.DataFrame(rates)
        atr = calculate_atr(df)
        
        # 2. Determine Multipliers
        if sym in METAL_SYMBOLS:
            sl_mult = 4.0
            tp_mult = 6.0
        else:
            sl_mult = 6.0
            tp_mult = 9.0
            
        # 3. Calculate Ideal Barriers
        sl_dist = sl_mult * atr
        tp_dist = tp_mult * atr
        
        new_sl = p.price_open - sl_dist if is_buy else p.price_open + sl_dist
        new_tp = p.price_open + tp_dist if is_buy else p.price_open - tp_dist
        
        # 4. Update Store
        t_id = str(p.ticket)
        thesis = thesis_store.get(t_id, {})
        thesis.update({
            "sl_barrier": new_sl,
            "tp_barrier": new_tp,
            "entry_atr": atr,
            "reanchored_at": datetime.now(timezone.utc).isoformat()
        })
        thesis_store[t_id] = thesis
        
        # 5. Sync Server
        success = sync_server_sl_tp(p, new_sl, new_tp)
        status = "SUCCESS" if success else "FAIL"
        
        print(f"[{status}] {sym} {p.ticket} | New SL: {new_sl:.5f} | New TP: {new_tp:.5f} | ATR: {atr:.5f}")
        updated_count += 1

    # Save
    with open(THESIS_FILE, 'w') as f:
        json.dump(thesis_store, f, indent=4)
        
    print(f"\n[DONE] Successfully re-anchored {updated_count} positions.")
    mt5.shutdown()

if __name__ == "__main__":
    main()
