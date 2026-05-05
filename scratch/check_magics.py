import MetaTrader5 as mt5
import pandas as pd

def check_magics():
    if not mt5.initialize():
        print("FAILED MT5 init")
        return
    
    positions = mt5.positions_get()
    if positions:
        df = pd.DataFrame([p._asdict() for p in positions])
        print(df[['ticket', 'symbol', 'magic', 'profit']].to_string(index=False))
    else:
        print("No positions.")
    mt5.shutdown()

if __name__ == "__main__":
    check_magics()
