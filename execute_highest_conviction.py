import MetaTrader5 as mt5
from arcticdb import Arctic
import math
import sys
from dataclasses import dataclass

@dataclass
class TradeRequest:
    symbol: str
    direction: str
    lot: float
    price: float
    sl: float
    tp: float

def get_candidate_trades(lib):
    """Iterates over Arctic library and extracts candidate trades sorted by conviction."""
    assets = []
    for sym in lib.list_symbols():
        if sym.endswith("_meta"):
            data = lib.read(sym).data
            if not data.empty:
                row = data.iloc[-1]
                base_sym = sym.replace("_meta", "")
                
                # Conviction extraction
                p_val = float(row.get("meta_conviction", row.get("xgb_p", 0.5)))
                direction = "BUY" if p_val >= 0.5 else "SELL"
                conviction = p_val if direction == "BUY" else (1.0 - p_val)
                
                if conviction >= 0.50:
                    assets.append({
                        "symbol": base_sym,
                        "direction": direction,
                        "conviction": conviction,
                        "hmm": row.get("wasserstein_state", "RANGE")
                    })
    return sorted(assets, key=lambda x: x["conviction"], reverse=True)

def calculate_atr_manual(rates):
    """Calculates ATR from a list of rate tuples."""
    if rates is None or len(rates) < 2:
        return None
    highs = [r[2] for r in rates]
    lows = [r[3] for r in rates]
    closes = [r[4] for r in rates]
    tr_list = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(rates))]
    atr = sum(tr_list) / len(tr_list)
    return atr

def calculate_sl_tp_lot(sym, direction, tick, info, acc, rates):
    """Calculates Stop Loss, Take Profit, and Lot size for a trade."""
    atr = calculate_atr_manual(rates)
    if atr is None:
        return None, None, None

    multiplier = 6.0
    if "BTC" in sym or "ETH" in sym: multiplier = 4.0
    elif any(idx in sym for idx in ["US30", "NAS100", "US2000", "SPX500"]): multiplier = 4.0
    elif "XAU" in sym or "XAG" in sym: multiplier = 4.0

    sl_dist = atr * multiplier
    tp_dist = sl_dist * 1.5

    price = tick.ask if direction == "BUY" else tick.bid
    digits = info.digits

    # Calculate base SL and TP
    sl = price - sl_dist if direction == "BUY" else price + sl_dist
    tp = price + tp_dist if direction == "BUY" else price - tp_dist

    # Dynamic spread-based protection
    spread = tick.ask - tick.bid
    min_sl_dist = spread * 1.5

    actual_sl_dist = abs(price - sl)
    if actual_sl_dist < min_sl_dist:
        print(f" -> Warning: Calculated SL dist ({actual_sl_dist:.5f}) is less than 1.5x spread ({min_sl_dist:.5f}). Padding SL.")
        if direction == "BUY":
            sl = price - min_sl_dist
            tp = price + (min_sl_dist * 1.5)
        else:
            sl = price + min_sl_dist
            tp = price - (min_sl_dist * 1.5)
    else:
        print(f" -> Calculated SL dist ({actual_sl_dist:.5f}) is safe against spread ({spread:.5f}).")

    sl = round(sl, digits)
    tp = round(tp, digits)

    # Position sizing
    sl_dist_points = abs(price - sl) / (info.point + 1e-12)
    point_val = info.trade_tick_value / (info.trade_tick_size / info.point)

    risk_usd = acc.balance * 0.02 * 0.5  # 2% risk with 0.5 multiplier -> 1% total risk
    raw_lot = risk_usd / (sl_dist_points * point_val + 1e-12)
    lot = math.floor(raw_lot / info.volume_step) * info.volume_step
    if lot <= 0:
        lot = info.volume_min

    if lot > info.volume_max:
        lot = info.volume_max

    return sl, tp, lot

def execute_trade(req: TradeRequest):
    """Sends a trade order to MT5 with filling mode retries."""
    action_type = mt5.ORDER_TYPE_BUY if req.direction == "BUY" else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": req.symbol,
        "volume": req.lot,
        "type": action_type,
        "price": req.price,
        "sl": req.sl,
        "tp": req.tp,
        "deviation": 20,
        "magic": 777777,
        "comment": "Sentinel Force Trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    print(" -> Sending order to MT5...")
    result = mt5.order_send(request)
    
    if result is None:
        print(" -> Error: mt5.order_send returned None")
        return False

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f" -> SUCCESS: Executed {req.symbol} {req.direction} at {req.price:.5f}")
        return True

    print(f" -> Execution failed: {result.retcode} - {result.comment}")
    # If filling mode issue, try standard fill types
    if result.retcode in [10030, 10022]:
        for alt_filling in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]:
            print(f" -> Retrying with alternative fill mode: {alt_filling}")
            request["type_filling"] = alt_filling
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f" -> SUCCESS on retry: Executed {req.symbol} {req.direction} at {req.price:.5f} with fill mode {alt_filling}")
                return True
    return False

def main():
    if not mt5.initialize():
        print("MT5 initialization failed")
        sys.exit(1)

    print("Retrieving candidate trades from oracle cache...")
    store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
    lib = store["oracle_cache"]

    assets = get_candidate_trades(lib)
    print(f"Found {len(assets)} potential trade candidates. Evaluating for execution...")
    
    acc = mt5.account_info()
    if acc is None:
        print("Failed to retrieve account info")
        mt5.shutdown()
        sys.exit(1)
        
    executed_any = False
    
    for a in assets:
        sym = a["symbol"]
        direction = a["direction"]
        conviction = a["conviction"]
        
        print(f"\nEvaluating: {sym} ({direction}) with conviction {conviction:.4f}")
        
        if not mt5.symbol_select(sym, True):
            print(f" -> Symbol select failed for {sym}. Skipping.")
            continue
            
        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if not info or not tick:
            print(f" -> Could not get symbol info/tick for {sym}. Skipping.")
            continue
            
        if info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
            print(f" -> Trading disabled for {sym}. Skipping.")
            continue

        existing_positions = mt5.positions_get(symbol=sym)
        if existing_positions is not None and len(existing_positions) > 0:
            print(f" -> Active position(s) already exist for {sym}. Skipping to avoid duplicate exposure.")
            continue

        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 20)
        if rates is None or len(rates) < 2:
            print(f" -> Failed to get hourly rates for ATR calculation on {sym}. Skipping.")
            continue
            
        sl, tp, lot = calculate_sl_tp_lot(sym, direction, tick, info, acc, rates)
        if sl is None:
            print(f" -> Failed to calculate trade parameters for {sym}. Skipping.")
            continue

        price = tick.ask if direction == "BUY" else tick.bid
        print(f" -> Prepared order: {direction} {lot} lots at {price:.5f} | SL: {sl} | TP: {tp}")
        
        req = TradeRequest(
            symbol=sym,
            direction=direction,
            lot=lot,
            price=price,
            sl=sl,
            tp=tp
        )

        if execute_trade(req):
            executed_any = True
            break
            
    if not executed_any:
        print("\nNo trade executed successfully.")
        sys.exit(1)
    else:
        print("\nForce execution completed successfully.")
        mt5.shutdown()

if __name__ == "__main__":
    main()
