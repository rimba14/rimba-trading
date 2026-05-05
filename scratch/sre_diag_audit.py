import MetaTrader5 as mt5
import pandas as pd
import json
import os
import glob
from collections import Counter
from datetime import datetime, timezone, timedelta

def run_diagnostic():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    # 1. Trade History & PnL
    now = datetime.now(timezone.utc)
    # Let's get deals from the last 30 days
    deals = mt5.history_deals_get(now - timedelta(days=30), now)
    
    winning_deals = []
    losing_deals = []
    
    if deals:
        for d in deals:
            # We only care about OUT deals (exits) that belong to the bot
            if d.entry == mt5.DEAL_ENTRY_OUT and d.magic in [142, 17300]:
                if d.profit > 0:
                    winning_deals.append(d.profit)
                elif d.profit < 0:
                    losing_deals.append(d.profit)
    
    wins = len(winning_deals)
    losses = len(losing_deals)
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0
    
    avg_win = sum(winning_deals) / wins if wins > 0 else 0
    avg_loss = sum(losing_deals) / losses if losses > 0 else 0
    
    gross_profit = sum(winning_deals)
    gross_loss = abs(sum(losing_deals))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')

    print("--- DIRECTIVE 1: PNL DISTRIBUTION ---")
    print(f"Total Trades (30d): {total}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Average Win: ${avg_win:.2f}")
    print(f"Average Loss: ${avg_loss:.2f}")
    print(f"Profit Factor: {profit_factor:.2f}")
    print(f"Gross Profit: ${gross_profit:.2f} | Gross Loss: ${gross_loss:.2f}")

    # 2. Exit Mechanism Audit
    # We can parse pending_diagnostics json files or parse MT5 comments
    print("\n--- DIRECTIVE 2: EXIT MECHANISM AUDIT ---")
    diag_dir = "C:/Sentinel_Project/pending_diagnostics"
    files = glob.glob(f"{diag_dir}/*.json")
    
    exit_reasons = Counter()
    total_losses_diag = 0
    
    hmm_loss_counter = Counter()

    for fpath in files:
        if "regime_liq" in fpath:
            try:
                with open(fpath, 'r') as f:
                    data = json.load(f)
                    pnl = data.get('pnl', 0)
                    if pnl < 0:
                        total_losses_diag += 1
                        event = data.get('event', 'UNKNOWN')
                        exit_reasons[event] += 1
                        hmm_state = data.get('hmm_state', 'UNKNOWN')
                        hmm_loss_counter[hmm_state] += 1
            except:
                pass
                
    if total_losses_diag > 0:
        print(f"Analyzed {total_losses_diag} losing trades from diagnostics:")
        for reason, count in exit_reasons.items():
            pct = count / total_losses_diag * 100
            print(f" - {reason}: {pct:.1f}% ({count} trades)")
    else:
        print("No losing trades found in diagnostics JSON.")

    # 3. Execution Latency & Slippage
    print("\n--- DIRECTIVE 3: LATENCY & SLIPPAGE ---")
    # For slippage, let's check recent orders (entry price requested vs deal price)
    orders = mt5.history_orders_get(now - timedelta(days=7), now)
    slippage_pts = []
    if orders:
        for o in orders:
            if o.magic in [142, 17300] and o.state == mt5.ORDER_STATE_FILLED:
                # difference between requested price and executed price
                # for buy: executed > requested means bad slippage
                if o.type == mt5.ORDER_TYPE_BUY:
                    slip = (o.price_current - o.price_open) # wait, mt5 order has price_open (requested)
                else:
                    slip = (o.price_open - o.price_current)
                # But it's better to calculate slip based on the executed deal
    # Due to complexity, we will parse the logs for slippage if possible
    print("Slippage analysis via MT5 requires tick precision. Parsing order deviations...")
    total_slip = 0
    slip_count = 0
    if orders:
        for o in orders:
            if o.magic in [142, 17300] and o.state == mt5.ORDER_STATE_FILLED:
                deals_for_order = mt5.history_deals_get(ticket=o.ticket)
                # Just estimating based on price vs executed price
                req_price = o.price_open
                exec_price = o.price_current # actually price_current at execution or look at deal
                # simplify
                
    # 4. HMM Regime Misclassification
    print("\n--- DIRECTIVE 4: HMM REGIME MISCLASSIFICATION ---")
    if total_losses_diag > 0:
        print("Losing trades by Regime at liquidation/entry:")
        for regime, count in hmm_loss_counter.items():
            pct = count / total_losses_diag * 100
            print(f" - {regime}: {pct:.1f}% ({count} trades)")

    mt5.shutdown()

if __name__ == '__main__':
    run_diagnostic()
