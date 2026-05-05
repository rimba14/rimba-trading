import MetaTrader5 as mt5

def check_tick():
    if not mt5.initialize():
        print("FAILED MT5 init")
        return
    
    symbol = "ADAUSD"
    tick = mt5.symbol_info_tick(symbol)
    print(f"Tick for {symbol}: {tick}")
    
    # Check if symbol needs suffix
    if not tick:
        for s in mt5.symbols_get():
            if "ADAUSD" in s.name:
                print(f"Alternative found: {s.name} | Tick: {mt5.symbol_info_tick(s.name)}")

    mt5.shutdown()

if __name__ == "__main__":
    check_tick()
