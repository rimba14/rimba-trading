import MetaTrader5 as mt5
import sys
from datetime import datetime

MAGIC_NUMBER = 142

def fix_naked_positions():
    if not mt5.initialize():
        print(f"MT5 Init failed: {mt5.last_error()}")
        return

    positions = mt5.positions_get()
    if not positions:
        print("No active positions found.")
        return

    for pos in positions:
        if pos.magic != MAGIC_NUMBER:
            continue
            
        tick = mt5.symbol_info_tick(pos.symbol)
        if not tick: continue
        info = mt5.symbol_info(pos.symbol)
        if not info: continue

        # Constitutional sizing baseline
        # We'll use a wider 2.0% stop for this emergency recovery to ensure we clear the spread
        price_for_sl = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        atr_proxy = price_for_sl * 0.02 # 2%
        
        sl_dist = 1.0 * atr_proxy
        tp_dist = 2.0 * atr_proxy
        
        if pos.type == mt5.ORDER_TYPE_BUY:
            new_sl = price_for_sl - sl_dist
            new_tp = price_for_sl + tp_dist
        else:
            new_sl = price_for_sl + sl_dist
            new_tp = price_for_sl - tp_dist
            
        # Normalize
        new_sl = round(new_sl, info.digits)
        new_tp = round(new_tp, info.digits)
        
        print(f"Fixing {pos.symbol} #{pos.ticket}: Type={pos.type} | Bid={tick.bid} | Ask={tick.ask}")
        print(f"  => Attempting SL={new_sl}, TP={new_tp}")
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": pos.ticket,
            "sl": new_sl,
            "tp": new_tp
        }
        
        res = mt5.order_send(request)
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"  => SUCCESS")
        else:
            print(f"  => FAILED: {res.retcode} - {res.comment}")

    mt5.shutdown()

if __name__ == "__main__":
    fix_naked_positions()
