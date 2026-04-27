import MetaTrader5 as mt5
import requests
from datetime import datetime, time
import logging

# --- CONFIGURATION ---
WEBHOOK_URL = "https://discord.com/api/webhooks/1496246026611458048/2ShGeHJjN-Z6XrydLjFy_hOz-iLWrqNHVfp3vanWHj7udTYXUGfglWvUdxJ0WqLyAK88"
WATCHLIST = ["EURUSD", "GBPUSD", "XAUUSD", "NAS100", "BTCUSD", "ETHUSD", "SP500", "GER40"]

def generate_eod_report():
    if not mt5.initialize():
        print("MT5 Initialization failed.")
        return

    # 1. Define Time Window (Midnight to Now)
    now = datetime.now()
    today_start = datetime.combine(now.date(), time.min)
    
    # 2. Fetch History
    deals = mt5.history_deals_get(today_start, now)
    
    if deals is None:
        print(f"No history found. Error code: {mt5.last_error()}")
        mt5.shutdown()
        return

    # 3. Filter and Calculate
    trading_deals = [d for d in deals if d.type in [mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL] and d.entry == mt5.DEAL_ENTRY_OUT]
    
    total_trades = len(trading_deals)
    net_pnl = sum(d.profit + d.commission + d.swap for d in trading_deals)
    wins = [d for d in trading_deals if d.profit > 0]
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0
    
    # Get Current Account State
    acc = mt5.account_info()
    equity = acc.equity if acc else 0.0
    
    # 4. Format Message
    status_emoji = "🚀" if net_pnl > 0 else "📉" if net_pnl < 0 else "⚖️"
    
    msg = (
        f"**{status_emoji} ADAPTIVE SENTINEL EOD REPORT**\n"
        f"**Date:** {now.strftime('%Y-%m-%d')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **Today's Activity:**\n"
        f"  └ Total Trades: {total_trades}\n"
        f"  └ Net PnL: ${net_pnl:.2f}\n"
        f"  └ Win Rate: {win_rate:.1f}%\n\n"
        f"💰 **Portfolio State:**\n"
        f"  └ Total Equity: ${equity:,.2f}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧠 *Sentinel Architecture v12.0 Deployment*"
    )
    
    # 5. Dispatch
    payload = {"content": msg}
    headers = {"Content-Type": "application/json"}
    try:
        import json
        response = requests.post(WEBHOOK_URL, data=json.dumps(payload), headers=headers, timeout=15)
        if response.status_code in [200, 201, 204]:
            print("EOD Report dispatched successfully to Discord.")
        else:
            logging.error(f"Webhook Failed! Status: {response.status_code} | Reason: {response.text}")
            print(f"Failed to send report. Status: {response.status_code}")
    except Exception as e:
        logging.error(f"Webhook Error: {e}")
        print(f"Webhook Error: {e}")

    mt5.shutdown()

if __name__ == "__main__":
    generate_eod_report()
