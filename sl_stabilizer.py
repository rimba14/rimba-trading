import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time

METAL_SYMBOLS = ["XAUUSD", "XAGUSD", "GOLD", "SILVER", "XPTUSD", "XPDUSD"]

def calculate_atr(symbol, timeframe=mt5.TIMEFRAME_H1, period=14):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, period + 1)
    if rates is None or len(rates) < period:
        return None
    df = pd.DataFrame(rates)
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]

def stabilize_sl():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    positions = mt5.positions_get()
    print(f"Auditing {len(positions)} positions...")

    for p in positions:
        sym = p.symbol
        ticket = p.ticket
        pos_type = p.type # 0=Buy, 1=Sell
        entry_price = p.price_open
        current_sl = p.sl

        atr = calculate_atr(sym)
        if atr is None:
            print(f"[{sym}] Could not calculate ATR. Skipping.")
            continue

        # Standards: 4.0x for Metals, 6.0x for others
        mult = 4.0 if sym.upper() in METAL_SYMBOLS else 6.0
        sl_dist = atr * mult
        
        # Calculate new SL
        if pos_type == mt5.POSITION_TYPE_BUY:
            new_sl = entry_price - sl_dist
        else:
            new_sl = entry_price + sl_dist

        # Round to tick size
        info = mt5.symbol_info(sym)
        if info:
            new_sl = round(new_sl / info.trade_tick_size) * info.trade_tick_size
        
        # Avoid modifying if already correct (within precision)
        if abs(new_sl - current_sl) < (info.trade_tick_size * 2):
            print(f"[{sym}] SL already compliant: {current_sl}")
            continue

        # Apply Modification
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": new_sl,
            "tp": p.tp # Keep existing TP
        }
        
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[{sym}] SL Updated: {current_sl} -> {new_sl} (Dist: {sl_dist:.5f})")
        else:
            print(f"[{sym}] Update Failed: {res.comment if res else 'Unknown'}")
            
    mt5.shutdown()

if __name__ == "__main__":
    stabilize_sl()
