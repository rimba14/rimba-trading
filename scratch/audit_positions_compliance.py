import MetaTrader5 as mt5
import sys
import pandas as pd

def audit_open_positions():
    print("=========================================================================")
    print("                 OPEN POSITIONS COMPLIANCE AUDIT                         ")
    print("=========================================================================")
    
    if not mt5.initialize():
        print("MT5 initialization failed.")
        return
        
    positions = mt5.positions_get()
    if positions is None or len(positions) == 0:
        print("No open positions found.")
        mt5.shutdown()
        return
        
    records = []
    for pos in positions:
        direction = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        records.append({
            "Ticket": pos.ticket,
            "Symbol": pos.symbol,
            "Dir": direction,
            "Volume": pos.volume,
            "Price": pos.price_open,
            "Current": pos.price_current,
            "SL": pos.sl,
            "TP": pos.tp,
            "PnL": pos.profit,
            "Magic": pos.magic
        })
        
    df = pd.DataFrame(records)
    print(df.to_string(index=False))
    
    naked_pos = df[(df["SL"] == 0.0) | (df["TP"] == 0.0)]
    if not naked_pos.empty:
        print("\n[WARNING] Found positions with missing SL/TP:")
        print(naked_pos.to_string(index=False))
    else:
        print("\n[OK] All positions have anchored SL/TP.")
        
    mt5.shutdown()

if __name__ == "__main__":
    audit_open_positions()
