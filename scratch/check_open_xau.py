import MetaTrader5 as mt5
import pandas as pd

def get_open_positions():
    if not mt5.initialize():
        print("MT5 Initialization failed")
        return

    positions = mt5.positions_get(symbol="XAUUSD")
    if positions:
        df = pd.DataFrame(list(positions), columns=positions[0]._asdict().keys())
        print(df[['symbol', 'type', 'volume', 'price_open', 'price_current', 'profit', 'comment']].to_string())
    else:
        print("No open XAUUSD positions")

    mt5.shutdown()

if __name__ == "__main__":
    get_open_positions()
