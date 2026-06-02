"""
adjust_positions_compliance.py
Checks all open MT5 positions against v30.96 constitutional rules:
1. Stop Loss distance >= 3.5 * ATR (H1, 20-period)
2. Take Profit distance >= 1.5 * Stop Loss distance

Adjusts non-compliant parameters in MT5 without liquidating positions.
"""
import os
import sys
import math
import MetaTrader5 as mt5

def main():
    if not mt5.initialize():
        print("[ERROR] Failed to initialize MT5")
        sys.exit(1)

    positions = mt5.positions_get()
    if not positions:
        print("[INFO] No open positions found.")
        mt5.shutdown()
        sys.exit(0)

    print(f"[INFO] Auditing {len(positions)} open positions...\n")

    for p in positions:
        sym = p.symbol
        ticket = p.ticket
        pos_type = p.type  # 0 = BUY, 1 = SELL
        price_open = p.price_open
        current_sl = p.sl
        current_tp = p.tp
        volume = p.volume

        info = mt5.symbol_info(sym)
        if not info:
            print(f"[SKIP] Ticket #{ticket} ({sym}): Could not query symbol info.")
            continue

        digits = info.digits

        # Calculate H1 ATR (20-period)
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 20)
        if rates is None or len(rates) < 2:
            print(f"[SKIP] Ticket #{ticket} ({sym}): Insufficient H1 rates history to compute ATR.")
            continue

        highs  = [r[2] for r in rates]
        lows   = [r[3] for r in rates]
        closes = [r[4] for r in rates]
        atr = sum([
            max(highs[i] - lows[i],
                abs(highs[i]  - closes[i-1]),
                abs(lows[i]   - closes[i-1]))
            for i in range(1, len(rates))
        ]) / (len(rates) - 1)

        min_sl_dist = atr * 3.5
        
        # 1. Stop Loss validation
        sl_adjusted = False
        sl_dist = abs(price_open - current_sl) if current_sl > 0 else 0.0
        
        target_sl = current_sl
        if current_sl == 0.0 or sl_dist < min_sl_dist:
            # SL is too tight or missing. Adjust to exactly 3.5 * ATR
            if pos_type == mt5.ORDER_TYPE_BUY:
                target_sl = round(price_open - min_sl_dist, digits)
            else:
                target_sl = round(price_open + min_sl_dist, digits)
            sl_adjusted = True
            print(f"[VIOLATION] Ticket #{ticket} ({sym} {'BUY' if pos_type==0 else 'SELL'}): SL distance {sl_dist:.5f} < 3.5*ATR ({min_sl_dist:.5f}). Adjusting SL {current_sl} -> {target_sl}")

        # Recalculate SL distance using target SL to establish TP floor
        actual_sl_dist = abs(price_open - target_sl)
        min_tp_dist = actual_sl_dist * 1.5

        # 2. Take Profit validation
        tp_adjusted = False
        tp_dist = abs(current_tp - price_open) if current_tp > 0 else 0.0
        
        target_tp = current_tp
        if current_tp == 0.0 or tp_dist < min_tp_dist:
            # TP is too close or missing. Adjust to exactly 1.5 * Stop Loss distance
            if pos_type == mt5.ORDER_TYPE_BUY:
                target_tp = round(price_open + min_tp_dist, digits)
            else:
                target_tp = round(price_open - min_tp_dist, digits)
            tp_adjusted = True
            print(f"[VIOLATION] Ticket #{ticket} ({sym} {'BUY' if pos_type==0 else 'SELL'}): TP distance {tp_dist:.5f} < 1.5*SL distance ({min_tp_dist:.5f}). Adjusting TP {current_tp} -> {target_tp}")

        # Send modification order if needed
        if sl_adjusted or tp_adjusted:
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": sym,
                "sl": target_sl,
                "tp": target_tp
            }
            res = mt5.order_send(request)
            if res.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"[FAILED] Adjusting Ticket #{ticket} ({sym}): retcode={res.retcode} | {res.comment}")
            else:
                print(f"[SUCCESS] Adjusted Ticket #{ticket} ({sym}) to compliant levels (SL={target_sl}, TP={target_tp})")
        else:
            print(f"[COMPLIANT] Ticket #{ticket} ({sym}): SL and TP comply with v30.96 guidelines.")

    mt5.shutdown()
    print("\n--- POSITION AUDIT COMPLETE ---")

if __name__ == "__main__":
    main()
