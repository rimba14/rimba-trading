import MetaTrader5 as mt5
from fastapi_sniper import calculate_kelly_lot
import logging

logging.basicConfig(level=logging.DEBUG)

if mt5.initialize():
    lot = calculate_kelly_lot("EURUSD", 0.90)
    print(f"Calculated Lot for EURUSD: {lot}")
else:
    print("MT5 Init Failed")
