import MetaTrader5 as mt5

if not mt5.initialize(): quit()

sym = "DOTUSD"
info = mt5.symbol_info(sym)
tick = mt5.symbol_info_tick(sym)

rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 20)
highs = [r[2] for r in rates]
lows = [r[3] for r in rates]
closes = [r[4] for r in rates]
atr = sum([max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(rates))]) / (len(rates) - 1)

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
