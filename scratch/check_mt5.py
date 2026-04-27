import MetaTrader5 as mt5
import pandas as pd

def check():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return
    
    print("MT5 Initialized")
    terminal_info = mt5.terminal_info()
    print(f"Connected: {terminal_info.connected}")
    print(f"Trade Allowed: {terminal_info.trade_allowed}")
    
    symbol = "EURUSD"
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 100)
    if rates is None:
        print(f"Failed to get rates for {symbol}. Error: {mt5.last_error()}")
    else:
        print(f"Successfully got {len(rates)} rates for {symbol}")
    
    mt5.shutdown()

if __name__ == "__main__":
    check()
