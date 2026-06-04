"""
execute_live_top5.py
Dynamically pulls the current top 5 conviction signals from oracle_cache
and executes them via MT5. Replaces hardcoded trade list.
"""
import math
import sys
import os
import MetaTrader5 as mt5
from arcticdb import Arctic

from tp_placement_engine import TPPlacementEngine, StructuralLevelResolver

class MT5OracleWrapper:
    def get_bars(self, symbol, timeframe, count):
        import MetaTrader5 as mt5
        tf = mt5.TIMEFRAME_D1 if timeframe == "D1" else mt5.TIMEFRAME_H4
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None: return []
        return [{"high": r[2], "low": r[3], "close": r[4]} for r in rates]

    def get_atr(self, symbol, timeframe, period, max_age_seconds):
        import MetaTrader5 as mt5
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, period + 1)
        if rates is None or len(rates) < 2: return 0.0
        highs = [r[2] for r in rates]
        lows = [r[3] for r in rates]
        closes = [r[4] for r in rates]
        atr = sum([
            max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            for i in range(1, len(rates))
        ]) / (len(rates) - 1)
        return atr

oracle_wrapper = MT5OracleWrapper()
level_resolver = StructuralLevelResolver(oracle_wrapper)
tp_engine = TPPlacementEngine(oracle_wrapper, level_resolver)

def verify_code_coherence():
    import subprocess
    try:
        active_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip().decode("utf-8")
        return active_hash
    except Exception:
        return "HASH_UNKNOWN"

INITIAL_HASH = verify_code_coherence()
HASH_FILE = "C:/Sentinel_Project/data/active_git_hash.txt"

# Execution Handshake Check
if INITIAL_HASH != "HASH_UNKNOWN":
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, "r") as f:
            disk_hash = f.read().strip()
        if disk_hash != INITIAL_HASH:
            print(f"[CRITICAL_VERSION_DRIFT_TERMINATION] Initialized hash signature {INITIAL_HASH} does not match the active configuration on disk {disk_hash}!")
            sys.exit("[CRITICAL_VERSION_DRIFT_TERMINATION] Mismatched version state. Execution halted.")
    else:
        try:
            os.makedirs(os.path.dirname(HASH_FILE), exist_ok=True)
            with open(HASH_FILE, "w") as f:
                f.write(INITIAL_HASH)
        except Exception as e:
            print(f"[WARNING] Could not initialize handshake file: {e}")

ARCTIC_URI = "lmdb://C:/Sentinel_Project/data/arctic_cache"
CONVICTION_THRESHOLD = 0.62
MAGIC_NUMBER = 777777

if not mt5.initialize():
    print("MT5 initialization failed")
    quit()

# ── Pull top 5 from oracle_cache ──────────────────────────────────────────────
store = Arctic(ARCTIC_URI)
lib   = store["oracle_cache"]
acc   = mt5.account_info()

# Get active open positions to prevent stacking
open_positions = mt5.positions_get()
active_positions = {}
if open_positions:
    for pos in open_positions:
        active_positions[pos.symbol] = "BUY" if pos.type == 0 else "SELL"

assets = []
for sym in lib.list_symbols():
    if not sym.endswith("_meta"):
        continue
    data = lib.read(sym).data
    if data.empty:
        continue
    row      = data.iloc[-1]
    base_sym = sym.replace("_meta", "")
    p_val    = float(row.get("meta_conviction", row.get("xgb_p", 0.5)))
    hmm_state = str(row.get("wasserstein_state", "RANGE")).upper()

    # Skip cold / quarantined or already active
    if p_val == 0.0 or p_val == 0.5 or "STAGNANT" in hmm_state or \
       "CLOSED" in hmm_state or "QUARANTINE" in hmm_state:
        continue
        
    if base_sym in active_positions:
        continue

    direction  = "BUY" if p_val >= 0.5 else "SELL"
    conviction = p_val if direction == "BUY" else (1.0 - p_val)

    if conviction >= CONVICTION_THRESHOLD:
        assets.append({
            "symbol":    base_sym,
            "direction": direction,
            "conviction": conviction,
            "hmm":       row.get("wasserstein_state", "RANGE"),
            "atr":       float(row.get("atr", 0.0)),
        })

assets = sorted(assets, key=lambda x: x["conviction"], reverse=True)[:5]

if not assets:
    print(f"INSUFFICIENT CONVICTION — no symbols >= {CONVICTION_THRESHOLD}")
    mt5.shutdown()
    sys.exit(0)


# ── Execute each signal ───────────────────────────────────────────────────────
print(f"\n--- SENTINEL LIVE EXECUTION | {len(assets)} SIGNALS ---")
for a in assets:
    sym       = a["symbol"]
    direction = a["direction"]
    conviction = a["conviction"]


    if not mt5.symbol_select(sym, True):
        print(f"[SKIP] {sym}: symbol not available in terminal")
        continue

    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if not info or not tick:
        print(f"[SKIP] {sym}: no tick data")
        continue

    # D1 ATR-based SL/TP (v30.98 Fix)
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 16)
    if rates is None or len(rates) < 2:
        print(f"[SKIP] {sym}: insufficient rate history")
        continue

    highs  = [r[2] for r in rates]
    lows   = [r[3] for r in rates]
    closes = [r[4] for r in rates]
    atr    = sum([
        max(highs[i] - lows[i],
            abs(highs[i]  - closes[i-1]),
            abs(lows[i]   - closes[i-1]))
        for i in range(1, len(rates))
    ]) / (len(rates) - 1)

    # ATR multiplier by asset class
    if any(x in sym for x in ["BTC", "ETH"]):
        mult = 4.0
    elif any(x in sym for x in ["US30", "NAS100", "US2000", "SPX500", "SP500"]):
        mult = 4.0
    elif any(x in sym for x in ["XAU", "XAG"]):
        mult = 4.0
    else:
        mult = 6.0

    sl_dist = atr * mult
    tp_dist = sl_dist * 1.5

    price  = tick.ask if direction == "BUY" else tick.bid
    digits = info.digits
    sl     = round(price - sl_dist if direction == "BUY" else price + sl_dist, digits)
    tp     = round(price + tp_dist if direction == "BUY" else price - tp_dist, digits)

    # Spread guard
    spread = tick.ask - tick.bid
    if direction == "BUY" and (tick.ask - sl) < spread * 1.5:
        sl = round(tick.ask - spread * 1.5, digits)
        tp = round(tick.ask + spread * 2.5, digits)
    elif direction == "SELL" and (sl - tick.bid) < spread * 1.5:
        sl = round(tick.bid + spread * 1.5, digits)
        tp = round(tick.bid - spread * 2.5, digits)

    # --- DIRECTIVE ZETA TP Placement ---
    dir_int = 1 if direction == "BUY" else -1
    
    crypto_keywords = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOT", "LINK", "AVAX", "LTC", "BCH", "TRX", "DOGE"}
    is_crypto = any(k in sym.upper() for k in crypto_keywords)
    
    if is_crypto:
        p_blend = conviction
        tp_dist_crypto = atr * (2.0 + 4.0 * ((max(p_blend, 0.60) - 0.60) / 0.40))
        if tp_dist_crypto < sl_dist * 1.5:
            tp_dist_crypto = sl_dist * 1.5
        tp = round(price + tp_dist_crypto if direction == "BUY" else price - tp_dist_crypto, digits)
        print(f"[ZETA OK] {sym} TP dynamically set to {tp} via Triple-Barrier")
    else:
        val_res = tp_engine.validate_tp_placement(
            symbol=sym,
            entry=price,
            sl=sl,
            proposed_tp=tp,
            direction=dir_int
        )
        if not val_res.is_valid:
            print(f"[ZETA REJECT] {sym} {direction} - {val_res.rejection_reason}")
            continue
        if val_res.final_tp is not None:
            tp = round(val_res.final_tp, digits)
            print(f"[ZETA OK] {sym} TP set structurally to {tp}")

    # Position sizing — 2% risk, 0.5 health multiplier
    sl_dist_points = sl_dist / (info.point + 1e-12)
    point_val      = info.trade_tick_value / (info.trade_tick_size / info.point + 1e-12)
    risk_usd       = acc.balance * 0.02 * 0.5
    raw_lot        = risk_usd / (sl_dist_points * point_val + 1e-12)
    lot            = math.floor(raw_lot / info.volume_step) * info.volume_step
    if lot <= 0:
        lot = info.volume_min

    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action":      mt5.TRADE_ACTION_DEAL,
        "symbol":      sym,
        "volume":      lot,
        "type":        order_type,
        "price":       price,
        "sl":          sl,
        "tp":          tp,
        "deviation":   20,
        "magic":       MAGIC_NUMBER,
        "comment":     f"Sentinel|{conviction:.2f}",
        "type_time":   mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[FAILED]  {sym} {direction} | retcode={result.retcode} | {result.comment}")
    else:
        print(f"[SUCCESS] {sym} {direction} | entry={price} | SL={sl} | TP={tp} | lot={lot} | conviction={conviction:.3f}")

mt5.shutdown()
print("\n--- EXECUTION COMPLETE ---")
