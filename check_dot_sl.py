import MetaTrader5 as mt5
import numpy as np

if not mt5.initialize(): quit()

sym = "DOTUSD"
info = mt5.symbol_info(sym)
tick = mt5.symbol_info_tick(sym)

rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 20)
if rates is None or len(rates) < 2:
    mt5.shutdown()
    quit()

highs = rates['high']
lows = rates['low']
closes = rates['close']

tr1 = highs[1:] - lows[1:]
tr2 = np.abs(highs[1:] - closes[:-1])
tr3 = np.abs(lows[1:] - closes[:-1])
atr = np.mean(np.maximum(tr1, np.maximum(tr2, tr3)))

sl_dist = atr * 6.0
spread = tick.ask - tick.bid

print(f"ATR: {atr:.5f}")
print(f"SL Distance: {sl_dist:.5f}")
print(f"Spread: {spread:.5f}")

adjusted_sl_dist = max(sl_dist, spread * 1.5)
print(f"Adjusted SL Distance: {adjusted_sl_dist:.5f}")

sl = tick.ask - adjusted_sl_dist
tp = tick.ask + (adjusted_sl_dist * 1.5)
print(f"New SL: {sl:.5f}")
print(f"New TP: {tp:.5f}")

mt5.shutdown()
