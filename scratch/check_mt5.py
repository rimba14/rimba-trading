import MetaTrader5 as mt5
if not mt5.initialize():
    print('Init failed')
    exit()
info = mt5.terminal_info()
print(f'Connected: {info.connected}')
print(f'TradeAllowed: {info.trade_allowed}')
print(f'TradeExpert: {info.trade_expert}')
mt5.shutdown()
