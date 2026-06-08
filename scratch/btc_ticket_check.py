import MetaTrader5 as mt5
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TICKET_CHECK")

def check_ticket():
    if not mt5.initialize():
        logger.error("MT5 init failed")
        return

    pos_id = 1389152365
    
    # Check open positions
    open_pos = mt5.positions_get(ticket=pos_id)
    if open_pos:
        logger.info(f"Ticket {pos_id} is STILL OPEN.")
    else:
        logger.info(f"Ticket {pos_id} is NOT OPEN.")
        
    # Check history deals
    deals = mt5.history_deals_get(position=pos_id)
    if deals:
        logger.info(f"Found {len(deals)} deals for position {pos_id}:")
        for d in deals:
            logger.info(f"Deal {d.ticket}: time={pd.to_datetime(d.time, unit='s')}, type={d.type}, entry={d.entry}, price={d.price}, profit={d.profit}, comment={d.comment}")
    else:
        logger.info(f"No history deals found for position {pos_id}.")

    mt5.shutdown()

if __name__ == "__main__":
    check_ticket()
