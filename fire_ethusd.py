import sys
import logging
import numpy as np

sys.path.append(r"C:\Sentinel_Project")
from fastapi_sniper import get_broker_adapter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def fire_eth_trade():
    symbol = "ETHUSD"
    adapter = get_broker_adapter(symbol)
    
    # 0.12 Lots, Direction = BUY
    logging.info(f"Preparing to route {symbol} BUY at 0.12 Lots via MT5...")
    
    try:
        ticket = adapter.execute_market_order(
            symbol=symbol,
            lots=0.12,
            direction="BUY",
            comment="SENTINEL_v30.70_PRIME_SIGNAL"
        )
        print(f"\n[EXECUTION SUCCESS] Trade successfully routed. Ticket ID: {ticket}")
    except Exception as e:
        print(f"\n[EXECUTION FAILED] Error routing trade: {e}")

if __name__ == "__main__":
    fire_eth_trade()
