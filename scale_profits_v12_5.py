import MetaTrader5 as mt5
import json
import os
import time
from datetime import datetime, timezone

def perform_scaling_and_lock():
    if not mt5.initialize():
        print("[-] MT5 Init failed")
        return

    # 1. Silver Profit Lock (XAGUSD)
    xag_pos = [p for p in mt5.positions_get(symbol="XAGUSD") if p.volume == 0.01]
    if xag_pos:
        p = xag_pos[0]
        tick = mt5.symbol_info_tick("XAGUSD")
        if tick:
            # Entry 70.918. Current 74.22.
            # We move SL to 73.918 (Locking in ~3.0 points of move)
            # 3.0 points * 5000 oz/lot? No, XAG standard is 5000 oz. 
            # 0.01 lots = 50 oz. 50 oz * 3.0 = $150. Correct.
            new_sl = 73.90
            from gitagent_action_layer import get_action_layer
            res = get_action_layer().modify_position_sltp("XAGUSD", p.ticket, new_sl, p.tp)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[+] XAGUSD: Profit locked at SL {new_sl} (~$150 guaranteed)")
            else:
                print(f"[-] XAGUSD Lock failed: {res.comment if res else 'Unknown error'}")

    # 2. Scaling (VISA, JPM, META)
    scaling_targets = {
        "VISA": 0.15,
        "JPM": 0.20,
        "META": 0.10
    }
    
    for sym, vol_to_close in scaling_targets.items():
        pos = mt5.positions_get(symbol=sym)
        if pos:
            p = pos[0]
            tick = mt5.symbol_info_tick(sym)
            if not tick: continue
            
            from gitagent_action_layer import get_action_layer
            res = get_action_layer().execute_smart_trade(sym, mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY, float(vol_to_close), comment="v12.5 Profit Scale", position_ticket=p.ticket)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[+] {sym}: Scaled out {vol_to_close} lots.")
            else:
                print(f"[-] {sym} Scale failed: {res.comment if res else 'Unknown error'}")


    mt5.shutdown()

if __name__ == "__main__":
    perform_scaling_and_lock()
