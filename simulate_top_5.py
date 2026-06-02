import MetaTrader5 as mt5
from arcticdb import Arctic
import math

mt5.initialize()

assets = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
acc = mt5.account_info()

print("\n--- TOP 5 HYPOTHETICAL READY TRADES (Simulated 0.85 Conviction due to Model Fail-Closed state) ---")
for sym in assets:
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if not info or not tick: continue
    
    # Calculate ATR
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 20)
    if rates is None or len(rates) < 2: continue
    highs = [r[2] for r in rates]
    lows = [r[3] for r in rates]
    closes = [r[4] for r in rates]
    atr = sum([max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(rates))]) / (len(rates) - 1)
    
    multiplier = 6.0
    sl_dist = atr * multiplier
    tp_dist = sl_dist * 1.5
    
    direction = "BUY"
    conviction = 0.85
    price = tick.ask
    digits = info.digits
    
    sl = round(price - sl_dist, digits)
    tp = round(price + tp_dist, digits)
    
    sl_dist_points = sl_dist / (info.point + 1e-12)
    point_val = info.trade_tick_value / (info.trade_tick_size / info.point)
    
    risk_usd = acc.balance * 0.02 * 0.5 # 0.5 health multiplier
    raw_lot = risk_usd / (sl_dist_points * point_val + 1e-12)
    lot = math.floor(raw_lot / info.volume_step) * info.volume_step
    if lot <= 0: lot = info.volume_min
    
    print(f"Asset: {sym}")
    print(f"Thesis: TREND | Direction: {direction} | Conviction: {conviction:.3f}")
    print(f"Entry: {price:.5f}")
    print(f"Calculated ATR: {atr:.5f}")
    print(f"Stop Loss: {sl} ({multiplier}x ATR Floor)")
    print(f"Take Profit: {tp} (1.5x SL Distance)")
    print(f"Sizing: {lot} lots (Max Risk Capped)")
    print("---------------------------------")
