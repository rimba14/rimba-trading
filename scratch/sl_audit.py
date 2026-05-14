import MetaTrader5 as mt5
if not mt5.initialize():
    print('MT5 Init Failed')
    exit()
positions = mt5.positions_get()
if not positions:
    print('NO_ACTIVE_POSITIONS')
else:
    print(f'AUDIT_START | Count: {len(positions)}')
    for p in positions:
        print(f'Symbol: {p.symbol} | Ticket: {p.ticket} | SL: {p.sl} | TP: {p.tp} | Type: {p.type}')
