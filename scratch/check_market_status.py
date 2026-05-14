import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd

def check_crypto_data():
    if not mt5.initialize():
        return "MT5 Init Failed"
    
    symbol = "BTCUSD"
    to_date = datetime.now()
    from_date = to_date - timedelta(minutes=10)
    ticks = mt5.copy_ticks_range(symbol, from_date, to_date, mt5.COPY_TICKS_ALL)
    
    if ticks is not None and len(ticks) > 0:
        mt5.shutdown()
        return f"SUCCESS: {len(ticks)} ticks for {symbol}"
    else:
        # Try finding a symbol that works
        all_symbols = mt5.symbols_get()
        working_sym = None
        for s in all_symbols:
            if "USD" in s.name:
                t = mt5.copy_ticks_range(s.name, from_date, to_date, mt5.COPY_TICKS_ALL)
                if t is not None and len(t) > 0:
                    working_sym = s.name
                    break
        mt5.shutdown()
        if working_sym:
            return f"SUCCESS: Found working symbol {working_sym}"
        else:
            return "FAILED: No ticks found for any USD symbol (Market likely closed or connection issues)"

if __name__ == "__main__":
    print(check_crypto_data())
