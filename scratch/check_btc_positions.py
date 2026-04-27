import MetaTrader5 as mt5
import pandas as pd
import json

def get_btc_positions():
    if not mt5.initialize():
        print("MT5 initialization failed")
        return

    positions = mt5.positions_get(symbol="BTCUSD")
    if positions is None:
        print("No BTCUSD positions found or error occurred.")
        mt5.shutdown()
        return

    if len(positions) == 0:
        # Try finding with suffix
        all_positions = mt5.positions_get()
        btc_pos = [p for p in all_positions if "BTC" in p.symbol]
        positions = btc_pos

    if len(positions) == 0:
        print("No active BTC positions found.")
    else:
        df = pd.DataFrame(list(positions), columns=positions[0]._asdict().keys())
        print("Current BTC Positions:")
        print(df[['symbol', 'type', 'volume', 'price_open', 'sl', 'tp', 'profit']])

    mt5.shutdown()

if __name__ == "__main__":
    get_btc_positions()
