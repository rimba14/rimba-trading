import MetaTrader5 as mt5
import pandas as pd

def forensic_audit():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    acc = mt5.account_info()
    equity = acc.equity
    risk_target = equity * 0.005 # 0.5%
    
    positions = mt5.positions_get()
    if not positions:
        print("No open positions.")
        return

    f_out = open("C:\\Sentinel_Project\\sl_audit_results.txt", "w", encoding="utf-8")
    print(f"--- ACCOUNT: ${equity:.2f} | 0.5% TARGET: ${risk_target:.2f} ---", file=f_out)
    print(f"{'SYMBOL':<10} | {'VOL':<5} | {'SL_DIST':<10} | {'RISK_$':<8} | {'%_RISK':<8} | {'RESULT'}", file=f_out)
    
    for p in positions:
        info = mt5.symbol_info(p.symbol)
        if not info: continue
        
        # Calculate distance to SL in points
        sl_dist_points = abs(p.price_open - p.sl) / info.point if p.sl > 0 else 0
        
        # Risk = volume * sl_dist_points * tick_value
        # Note: This is an approximation of the point value.
        # More accurately: (LotSize * units_per_lot) * distance
        # Or using MT5's tick_value:
        risk_usd = (sl_dist_points * info.trade_tick_value) * (p.volume / info.volume_step if info.volume_step > 0 else p.volume * 100)
        # Re-calc simpler:
        points = abs(p.price_open - p.sl) / info.trade_tick_size if p.sl > 0 else 0
        risk_usd = points * info.trade_tick_value * (p.volume / info.volume_step * (info.volume_step / 1.0)) # heuristic check
        
        # Correct for USD base etc - just use the trade_tick_value approach
        actual_risk_usd = (abs(p.price_open - p.sl) / info.trade_tick_size) * info.trade_tick_value * (p.volume / info.volume_step) * info.volume_step

        risk_pct = (actual_risk_usd / equity) * 100
        status = "❌ OVER-RISK" if actual_risk_usd > (risk_target * 1.2) else "✅ OK"
        
        print(f"{p.symbol:<10} | {p.volume:<5} | {abs(p.price_open-p.sl):<10.5f} | ${actual_risk_usd:<7.2f} | {risk_pct:<7.2f}% | {status}", file=f_out)

    f_out.close()
    mt5.shutdown()

if __name__ == "__main__":
    forensic_audit()
