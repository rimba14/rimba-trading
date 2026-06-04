import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 initialization failed")
    quit()

syms = mt5.symbols_get(group="*HK50*")
if syms:
    for s in syms:
        print(s.name, "Visible:", s.visible)
else:
    print("No HK50 symbols found")

tick = mt5.symbol_info_tick("HK50")
print("HK50 tick:", tick)

info = mt5.symbol_info("HK50")
if info:
    print("HK50 trade mode:", info.trade_mode)
    print("HK50 session info:", info.session_deals, info.session_buy_orders)

mt5.shutdown()
