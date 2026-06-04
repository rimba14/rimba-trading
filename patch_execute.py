import sys

FILE_PATH = "c:\\Users\\ADMIN\\.antigravity\\rimba-trading\\execute_live_top5.py"

with open(FILE_PATH, 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Imports
if 'TPPlacementEngine' not in code:
    imports = """
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
"""
    code = code.replace("from arcticdb import Arctic\n", "from arcticdb import Arctic\n" + imports, 1)

# 2. Replacing the mechanical TP calculation
old_logic = """    # Spread guard
    spread = tick.ask - tick.bid
    if direction == "BUY" and (tick.ask - sl) < spread * 1.5:
        sl = round(tick.ask - spread * 1.5, digits)
        tp = round(tick.ask + spread * 2.5, digits)
    elif direction == "SELL" and (sl - tick.bid) < spread * 1.5:
        sl = round(tick.bid + spread * 1.5, digits)
        tp = round(tick.bid - spread * 2.5, digits)"""

new_logic = """    # Spread guard
    spread = tick.ask - tick.bid
    if direction == "BUY" and (tick.ask - sl) < spread * 1.5:
        sl = round(tick.ask - spread * 1.5, digits)
        tp = round(tick.ask + spread * 2.5, digits)
    elif direction == "SELL" and (sl - tick.bid) < spread * 1.5:
        sl = round(tick.bid + spread * 1.5, digits)
        tp = round(tick.bid - spread * 2.5, digits)

    # --- DIRECTIVE ZETA TP Placement ---
    dir_int = 1 if direction == "BUY" else -1
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
        print(f"[ZETA OK] {sym} TP set structurally to {tp}")"""

if '# --- DIRECTIVE ZETA TP Placement ---' not in code:
    code = code.replace(old_logic, new_logic)

with open(FILE_PATH, 'w', encoding='utf-8') as f:
    f.write(code)

print("Patched execute_live_top5.py for DIRECTIVE ZETA successfully.")
