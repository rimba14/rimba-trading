import MetaTrader5 as mt5
import json
import os

def check_saturation():
    if not mt5.initialize():
        print("MT5 Init failed")
        return

    pos = mt5.positions_get()
    acc = mt5.account_info()
    
    if not pos or not acc:
        print("No active positions or account info.")
        return

    THESIS_FILE = "C:\\Sentinel_Project\\position_thesis.json"
    thesis = {}
    if os.path.exists(THESIS_FILE):
        with open(THESIS_FILE, 'r') as f:
            thesis = json.load(f)

    print(f"\n[*] SENTINEL RISK AUDIT | Balance: ${acc.balance:.2f} | Equity: ${acc.equity:.2f}")
    print("-" * 75)
    print(f"{'Symbol':<10} | {'Ticket':<12} | {'Srv_SL':<10} | {'Ths_SL':<10} | {'Risk USD':<10}")
    print("-" * 75)

    total_risk = 0
    for p in pos:
        info = mt5.symbol_info(p.symbol)
        sl = p.sl
        source = "Server"
        
        # Check against thesis if server SL is 0 or different
        ths_sl = 0
        if str(p.ticket) in thesis:
            ths_sl = thesis[str(p.ticket)].get('sl_barrier', 0)
        
        effective_sl = sl if sl > 0 else ths_sl
        if effective_sl == 0:
            # Absolute worst case (10% move)
            risk = p.volume * p.price_open * 0.1
        else:
            dist = abs(p.price_open - effective_sl)
            risk = (dist / info.trade_tick_size) * info.trade_tick_value * p.volume if info.trade_tick_size > 0 else dist * p.volume
        
        total_risk += risk
        print(f"{p.symbol:<10} | {p.ticket:<12} | {sl:<10.5f} | {ths_sl:<10.5f} | ${risk:<8.2f}")

    risk_cap_dollars = acc.balance * 0.12
    saturation = (total_risk / risk_cap_dollars) * 100
    
    print("-" * 75)
    print(f"COMMITTED RISK (VaR-lite): ${total_risk:.2f}")
    print(f"RISK BUDGET (12% of Bal):  ${risk_cap_dollars:.2f}")
    print(f"SATURATION LEVEL:          {saturation:.1f}%")
    
    if total_risk >= risk_cap_dollars:
        print("\nSTATUS: !!! RISK SATURATED !!! (Budget Exhausted)")
    else:
        print(f"\nSTATUS: CAPACITY OK (${risk_cap_dollars - total_risk:.2f} remaining)")

if __name__ == "__main__":
    check_saturation()
