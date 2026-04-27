import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 Initialization Failed")
    quit()

symbols = ['AZN', 'NAS100', 'AAPL', 'NVIDIA', 'TSLA']
for s in symbols:
    si = mt5.symbol_info(s)
    if si:
        tick = mt5.symbol_info_tick(s)
        price = tick.ask if tick else 0
        print(f"{s}: MinVol={si.volume_min} | Price={price} | Value={si.trade_contract_size}")
    else:
        print(f"{s} NOT FOUND")

mt5.shutdown()
