import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 Initialization Failed")
    quit()

indices = ['NAS100', 'SP500', 'DJ30', 'UK100', 'GER40', 'SPI200']
for s in indices:
    si = mt5.symbol_info(s)
    if si:
        print(f"{s}: MinVol={si.volume_min} | Step={si.volume_step} | Type={si.trade_calc_mode}")
    else:
        print(f"{s} NOT FOUND")

mt5.shutdown()
