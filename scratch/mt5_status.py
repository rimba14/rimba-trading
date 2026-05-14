import MetaTrader5 as mt5
import sys
from datetime import datetime

if not mt5.initialize():
    print("MT5 Init Failed")
    sys.exit(1)

pos = mt5.positions_get()
if pos:
    for p in pos:
        t = datetime.fromtimestamp(p.time)
        print(f" - {p.symbol} #{p.ticket} {p.type} {p.volume} time={t} profit={p.profit}")
else:
    print("No open positions")

mt5.shutdown()
