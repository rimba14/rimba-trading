import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

if not mt5.initialize():
    print("MT5 Initialization Failed")
    quit()

acc = mt5.account_info()
if acc:
    print(f"ACCOUNT: Balance={acc.balance} | Equity={acc.equity} | Profit={acc.profit} | MarginLevel={acc.margin_level}")

pos = mt5.positions_get()
if pos:
    print(f"\nACTIVE POSITIONS ({len(pos)}):")
    df_pos = pd.DataFrame(list(pos), columns=pos[0]._asdict().keys())
    print(df_pos[['symbol', 'type', 'volume', 'price_open', 'price_current', 'profit']].to_string())
else:
    print("\nNo active positions.")

# Today's deals
from_date = datetime.now() - timedelta(days=1)
deals = mt5.history_deals_get(from_date, datetime.now())
if deals:
    print(f"\nRECENT DEALS (Last 24h):")
    df_deals = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    # 0 = Buy/Entry, 1 = Sell/Exit usually for deals? No, type 0=BUY, 1=SELL
    # ENTRY = 0, EXIT = 1 in 'entry' column
    df_exits = df_deals[df_deals['entry'] == 1]
    print(f"Closed Trades: {len(df_exits)}")
    print(f"Total Closed PnL: {df_exits['profit'].sum():.2f}")
    if len(df_exits) > 0:
        win_rate = len(df_exits[df_exits['profit'] > 0]) / len(df_exits)
        print(f"Win Rate: {win_rate:.1%}")
else:
    print("\nNo deals in last 24h.")

mt5.shutdown()
