import MetaTrader5 as mt5
import sys

def run_diagnostic():
    print("=== MT5 SLTP MODIFICATION DIAGNOSTIC SWEEP ===")
    if not mt5.initialize():
        print(f"[FATAL] MT5 initialize failed: {mt5.last_error()}")
        sys.exit(1)
        
    positions = mt5.positions_get()
    if positions is None:
        print(f"[ERROR] Failed to get positions: {mt5.last_error()}")
        mt5.shutdown()
        return

    print(f"Total open positions found: {len(positions)}")
    modified_count = 0
    
    for pos in positions:
        print(f"\nEvaluating Position #{pos.ticket} on {pos.symbol} (Type: {pos.type}, SL: {pos.sl}, TP: {pos.tp})")
        if pos.tp == 0.0 or pos.sl == 0.0:
            info = mt5.symbol_info(pos.symbol)
            if not info:
                print(f"  [WARN] Could not retrieve symbol info for {pos.symbol}")
                continue
                
            digits = info.digits
            price = pos.price_open
            
            # Estimate 1% price distance
            distance = price * 0.01
            
            # SL calculation: must not be 0.0
            if pos.sl != 0.0:
                rounded_sl = round(pos.sl, digits)
            else:
                raw_sl = price - distance if pos.type == 0 else price + distance
                rounded_sl = round(raw_sl, digits)
                
            # TP calculation: 3x distance proxy
            tp_dist = distance * 3.0
            raw_tp = price + tp_dist if pos.type == 0 else price - tp_dist
            rounded_tp = round(raw_tp, digits)
            
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "position": pos.ticket,  # CRITICAL: Use 'position', NOT 'order'
                "sl": float(rounded_sl),
                "tp": float(rounded_tp)
            }
            
            print(f"  Dispatching modification request: {request}")
            result = mt5.order_send(request)
            
            if result is None:
                print(f"  [RESULT: NONE] mt5.order_send failed. last_error: {mt5.last_error()}")
            else:
                print(f"  [RESULT: RETURNED] Retcode: {result.retcode} | Comment: {result.comment}")
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    modified_count += 1
                    
    print(f"\nDiagnostic finished. Successfully applied to {modified_count} positions.")
    mt5.shutdown()

if __name__ == "__main__":
    run_diagnostic()
