import MetaTrader5 as mt5

def check():
    mt5.initialize()
    symbols = ["EURUSD", "CADCHF", "BTCUSD"]
    for s in symbols:
        info = mt5.symbol_info(s)
        tick = mt5.symbol_info_tick(s)
        if info and tick:
            spread = tick.ask - tick.bid
            stops = info.trade_stops_level * info.point
            print(f"{s}: spread={spread:.5f}, stops_level={stops:.5f}")

check()
