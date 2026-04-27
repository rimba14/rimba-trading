import MetaTrader5 as mt5
from datetime import datetime, timedelta

mt5.initialize()
info = mt5.account_info()

with open("C:\\Sentinel_Project\\\emergency_report.txt", "w", encoding="utf-8") as f:
    f.write(f"=== EMERGENCY BALANCE REPORT ===\n")
    f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    f.write(f"Balance: ${info.balance:.2f} | Equity: ${info.equity:.2f} | Profit: ${info.profit:.2f}\n")
    f.write(f"Margin Level: {info.margin_level:.1f}%\n\n")
    
    # Pull deals from the last 5 hours (since v8.3 deploy)
    from_date = datetime.now() - timedelta(hours=5)
    to_date = datetime.now() + timedelta(hours=1)
    deals = mt5.history_deals_get(from_date, to_date)
    
    if deals:
        exits = [d for d in deals if d.entry == 1]
        total_pnl = sum(d.profit + d.commission + d.swap for d in exits)
        sl_exits = [d for d in exits if d.reason == 4]
        tp_exits = [d for d in exits if d.reason == 5]
        expert_exits = [d for d in exits if d.reason == 3]
        
        f.write(f"=== DEALS SINCE v8.3 DEPLOY (last 5h) ===\n")
        f.write(f"Total exits: {len(exits)} | Net P&L: ${total_pnl:.2f}\n")
        f.write(f"SL: {len(sl_exits)} | TP: {len(tp_exits)} | Expert: {len(expert_exits)}\n\n")
        
        f.write(f"--- ALL EXITS (worst first) ---\n")
        for d in sorted(exits, key=lambda x: x.profit):
            ts = datetime.fromtimestamp(d.time).strftime("%H:%M")
            reason_map = {0:"CLIENT",1:"MOBILE",2:"WEB",3:"EXPERT",4:"SL",5:"TP",6:"SO"}
            rl = reason_map.get(d.reason, f"R{d.reason}")
            total = d.profit + d.commission + d.swap
            f.write(f"  {ts} | {d.symbol:12s} | {'BUY' if d.type==0 else 'SELL':4s} | {d.volume} lot | PnL: ${d.profit:>8.2f} | Comm: ${d.commission:.2f} | Swap: ${d.swap:.2f} | Net: ${total:.2f} | {rl}\n")
        
        # Check for repeated symbols
        sym_counts = {}
        for d in exits:
            sym = d.symbol
            if sym not in sym_counts:
                sym_counts[sym] = {"count": 0, "pnl": 0.0, "sl": 0, "tp": 0}
            sym_counts[sym]["count"] += 1
            sym_counts[sym]["pnl"] += d.profit
            if d.reason == 4: sym_counts[sym]["sl"] += 1
            if d.reason == 5: sym_counts[sym]["tp"] += 1
        
        f.write(f"\n--- SYMBOL BREAKDOWN ---\n")
        for s, v in sorted(sym_counts.items(), key=lambda x: x[1]["pnl"]):
            f.write(f"  {s:12s}: {v['count']} trades | PnL: ${v['pnl']:.2f} | SL:{v['sl']} TP:{v['tp']}\n")
    else:
        f.write("No deals found in the last 5 hours.\n")
    
    # Current open positions
    f.write(f"\n=== OPEN POSITIONS ===\n")
    positions = mt5.positions_get()
    if positions:
        total_floating = sum(p.profit for p in positions)
        f.write(f"Total open: {len(positions)} | Floating P&L: ${total_floating:.2f}\n\n")
        for p in positions:
            sl_dist = abs(p.price_open - p.sl) if p.sl > 0 else 0
            tp_dist = abs(p.tp - p.price_open) if p.tp > 0 else 0
            rr = tp_dist / sl_dist if sl_dist > 0 else 0
            f.write(f"  {p.symbol:12s} | {'BUY' if p.type==0 else 'SELL':4s} | {p.volume} lot | PnL ${p.profit:>8.2f} | SL:{p.sl:.5f} TP:{p.tp:.5f} | R:R={rr:.2f} | Comment:{p.comment}\n")
    else:
        f.write("  None.\n")

mt5.shutdown()
print("Emergency report written.")
