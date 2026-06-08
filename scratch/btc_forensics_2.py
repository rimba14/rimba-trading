import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BTC_FORENSICS_2")

def do_forensics():
    if not mt5.initialize():
        logger.error("MT5 init failed")
        return

    # Get deals from the last 2 days
    to_date = datetime.now()
    from_date = to_date - timedelta(days=2)
    
    deals = mt5.history_deals_get(from_date, to_date)
    if not deals:
        logger.error("No deals found in history.")
        mt5.shutdown()
        return
        
    df_deals = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    
    # Filter for BTCUSD
    df_btc = df_deals[df_deals['symbol'].str.contains("BTCUSD", case=False, na=False)].copy()
    
    if df_btc.empty:
        logger.error("No BTCUSD deals found in the last 2 days.")
        mt5.shutdown()
        return

    # Look for the trade taken on June 4th
    df_exits = df_btc[(df_btc['entry'] == 1)].copy()
    
    if df_exits.empty:
        logger.error("No exits found for BTC in the last 2 days. Maybe it's still open?")
    else:
        df_exits = df_exits.sort_values(by='time', ascending=False)
        for _, row in df_exits.iterrows():
            pos_id = row['position_id']
            exit_time = pd.to_datetime(row['time'], unit='s')
            exit_price = row['price']
            profit = row['profit']
            comment = row['comment']
            
            entry_deals = df_btc[(df_btc['position_id'] == pos_id) & (df_btc['entry'] == 0)]
            if not entry_deals.empty:
                entry_time = pd.to_datetime(entry_deals.iloc[-1]['time'], unit='s')
                logger.info(f"Position: {pos_id} | Entry Time: {entry_time} | Exit Time: {exit_time} | Profit: {profit} | Comment: {comment}")
            else:
                logger.info(f"Position: {pos_id} | Exit Time: {exit_time} | Profit: {profit} | Comment: {comment}")

    # Check if the ticket 1389152365 is currently open
    positions = mt5.positions_get(symbol="BTCUSD")
    if positions:
        logger.info("--- OPEN BTCUSD POSITIONS ---")
        for pos in positions:
            logger.info(f"Open Pos ID: {pos.ticket} | Time: {pd.to_datetime(pos.time, unit='s')} | Price: {pos.price_open}")
    else:
        logger.info("No open BTCUSD positions.")

    mt5.shutdown()

if __name__ == "__main__":
    do_forensics()
