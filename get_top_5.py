import MetaTrader5 as mt5
from arcticdb import Arctic
import math

mt5.initialize()
store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
lib = store["oracle_cache"]

assets = []
for sym in lib.list_symbols():
    if sym.endswith("_meta"):
        data = lib.read(sym).data
        if not data.empty:
            row = data.iloc[-1]
            base_sym = sym.replace("_meta", "")
            
            # Conviction extraction
            p_val = float(row.get("meta_conviction", row.get("xgb_p", 0.5)))
            
            # Veto cold start or quarantined assets
            hmm_state = str(row.get("wasserstein_state", "RANGE")).upper()
            if p_val == 0.0 or p_val == 0.5 or "STAGNANT" in hmm_state or "CLOSED" in hmm_state or "QUARANTINE" in hmm_state:
                continue
                
            direction = "BUY" if p_val >= 0.5 else "SELL"
            conviction = p_val if direction == "BUY" else (1.0 - p_val)
            
            if conviction >= 0.62: # Minimum conviction threshold (RF model output range: 0.55-0.85)
                assets.append({
                    "symbol": base_sym,
                    "direction": direction,
                    "conviction": conviction,
                    "hmm": row.get("wasserstein_state", "RANGE")
                })

# Sort by conviction descending
assets = sorted(assets, key=lambda x: x["conviction"], reverse=True)[:5]
acc = mt5.account_info()

if len(assets) == 0:
    # Debug: show what the top scores actually were
    import arcticdb as adb
    ac2 = adb.Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
    lib2 = ac2.get_library("oracle_cache", create_if_missing=False)
    top_scores = []
    for sym2 in lib2.list_symbols():
        if sym2.endswith("_meta"):
            d2 = lib2.read(sym2).data
            if not d2.empty:
                r2 = d2.iloc[-1]
                p2 = float(r2.get("meta_conviction", 0.5))
                top_scores.append((sym2.replace("_meta",""), p2))
    top_scores.sort(key=lambda x: x[1], reverse=True)
    print("INSUFFICIENT CONVICTION FOR 5 SLOTS. ALL ASSETS QUARANTINED.")
    print(f"Top 5 live convictions (threshold=0.62): {top_scores[:5]}")
    import sys
    sys.exit(0)

print("\n--- TOP 5 READY TRADES ---")
for a in assets:
    sym = a["symbol"]
    mt5.symbol_select(sym, True)
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
    if "BTC" in sym or "ETH" in sym: multiplier = 4.0
    elif "US30" in sym or "NAS100" in sym or "US2000" in sym or "SPX500" in sym: multiplier = 4.0
    elif "XAU" in sym or "XAG" in sym: multiplier = 4.0
    
    sl_dist = atr * multiplier
    tp_dist = sl_dist * 1.5
    
    price = tick.ask if a["direction"] == "BUY" else tick.bid
    digits = info.digits
    
    sl = round(price - sl_dist if a["direction"] == "BUY" else price + sl_dist, digits)
    tp = round(price + tp_dist if a["direction"] == "BUY" else price - tp_dist, digits)
    
    sl_dist_points = sl_dist / (info.point + 1e-12)
    point_val = info.trade_tick_value / (info.trade_tick_size / info.point)
    
    risk_usd = acc.balance * 0.02 * 0.5 # 0.5 health multiplier
    raw_lot = risk_usd / (sl_dist_points * point_val + 1e-12)
    lot = math.floor(raw_lot / info.volume_step) * info.volume_step
    if lot <= 0: lot = info.volume_min
    
    print(f"Asset: {sym}")
    print(f"Thesis: {a['hmm']} | Direction: {a['direction']} | Conviction: {a['conviction']:.3f}")
    print(f"Entry: {price:.5f}")
    print(f"Stop Loss: {sl}")
    print(f"Take Profit: {tp}")
    print(f"Sizing: {lot}")
    print("---------------------------------")
