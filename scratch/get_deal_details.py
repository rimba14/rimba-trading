import sys
import os
import pandas as pd
from datetime import datetime, timedelta

sys.path.append(r"C:\Sentinel_Project")
import MetaTrader5 as mt5
import git_arctic

def main():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    ticket = 1322005892
    from_date = datetime.now() - timedelta(days=5)
    to_date = datetime.now() + timedelta(days=1)
    
    deals = mt5.history_deals_get(from_date, to_date)
    if not deals:
        print("No deals found")
        return
        
    df_deals = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    match_deals = df_deals[df_deals['position_id'] == ticket]
    
    print("=== DEAL DETAILS ===")
    for idx, row in match_deals.iterrows():
        print(f"Ticket: {row['ticket']}")
        print(f"  Time (Local): {datetime.fromtimestamp(row['time'])}")
        print(f"  Time (Raw): {row['time']}")
        print(f"  Symbol: {row['symbol']}")
        print(f"  Type: {'BUY' if row['type'] == 0 else 'SELL'}")
        print(f"  Entry: {'IN' if row['entry'] == 0 else 'OUT'}")
        print(f"  Volume: {row['volume']}")
        print(f"  Price: {row['price']}")
        print(f"  Profit: {row['profit']}")
        print(f"  Comment: {row['comment']}")
        print(f"  Swap: {row.get('swap', 0.0)}")
        print(f"  Commission: {row.get('commission', 0.0)}")
        
        # Query orders history to get SL/TP at entry
        order_id = row['order']
        orders = mt5.history_orders_get(ticket=order_id)
        if orders:
            ord_info = orders[0]
            print(f"  Order SL: {ord_info.sl}")
            print(f"  Order TP: {ord_info.tp}")
            print(f"  Order Price: {ord_info.price_open}")
        print("-" * 40)

    # Let's get the entry time
    entry_row = match_deals[match_deals['entry'] == 0]
    if not entry_row.empty:
        entry_time = entry_row.iloc[0]['time']
        print(f"Entry Timestamp: {entry_time} ({datetime.fromtimestamp(entry_time)})")
        
        # Query database around the entry time
        print("\n=== ARCTIC DATABASE RECORDS AROUND ENTRY ===")
        store = git_arctic.get_arctic()
        lib = store['oracle_cache']
        
        # Read the meta, hmm, and kronos history
        try:
            m_df = lib.read("EURJPY_meta").data
            m_near = m_df[abs(m_df['timestamp'] - entry_time) < 1800]
            print("\nEURJPY_meta:")
            print(m_near.to_string())
        except Exception as e:
            print(f"Meta err: {e}")
            
        try:
            h_df = lib.read("EURJPY_hmm").data
            h_near = h_df[abs(h_df['timestamp'] - entry_time) < 1800]
            print("\nEURJPY_hmm:")
            print(h_near.to_string())
        except Exception as e:
            print(f"HMM err: {e}")
            
        try:
            k_df = lib.read("EURJPY_kronos").data
            k_near = k_df[abs(k_df['timestamp'] - entry_time) < 1800]
            print("\nEURJPY_kronos:")
            print(k_near.to_string())
        except Exception as e:
            print(f"Kronos err: {e}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
