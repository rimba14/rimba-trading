import MetaTrader5 as mt5
import math

mt5.initialize()

# Get all open positions
positions = mt5.positions_get(symbol="EURUSD")
if not positions:
    print("No open EURUSD positions found.")
else:
    pos = positions[0]
    print(f"Current EURUSD SL: {pos.sl}")
    
    # Calculate proper ATR
    rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 20)
    highs = [r[2] for r in rates]
    lows = [r[3] for r in rates]
    closes = [r[4] for r in rates]
    atr = 0
    for i in range(1, len(rates)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        atr += tr
    atr = atr / (len(rates) - 1)
    print(f"Calculated ATR: {atr:.5f}")
    
    # Floor distance: Forex multiplier = 6.0
    safe_dist = atr * 6.0
    
    new_sl = pos.price_open - safe_dist if pos.type == mt5.ORDER_TYPE_BUY else pos.price_open + safe_dist
    new_tp = pos.price_open + (safe_dist * 1.5) if pos.type == mt5.ORDER_TYPE_BUY else pos.price_open - (safe_dist * 1.5)
    
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": "EURUSD",
        "position": pos.ticket,
        "sl": round(new_sl, 5),
        "tp": round(new_tp, 5)
    }
    result = mt5.order_send(request)
    print(f"MT5 Modification Result: {result.comment if result else 'Failed'} - SL: {round(new_sl, 5)}, TP: {round(new_tp, 5)}")
