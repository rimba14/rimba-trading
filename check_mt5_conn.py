import MetaTrader5 as mt5
if not mt5.initialize():
    print("MT5 init failed")
    quit()
    
terminal = mt5.terminal_info()
if terminal:
    print("Terminal connected:", terminal.connected)
    print("Trade allowed:", terminal.trade_allowed)
    print("Connected server:", terminal.community_connection)
else:
    print("Terminal info not available")
    
account = mt5.account_info()
if account:
    print("Account Server:", account.server)
    print("Account Balance:", account.balance)
else:
    print("Account info not available")
    
mt5.shutdown()
