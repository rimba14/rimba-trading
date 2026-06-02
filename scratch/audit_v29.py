import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta, timezone
from arcticdb import Arctic
import json
import os
import re

def get_target_trade(target_ticket=1329003926):
    if not mt5.initialize():
        return None
    deals = mt5.history_deals_get(datetime(2026, 1, 1), datetime.now() + timedelta(days=1))
    target_deals = [d for d in deals if d.position_id == target_ticket]
    if target_deals: return target_deals
    pos_deals = {}
    for d in deals:
        if d.position_id not in pos_deals: pos_deals[d.position_id] = []
        pos_deals[d.position_id].append(d)
    closed_losing = []
    for pid, d_list in pos_deals.items():
        in_deals = [d for d in d_list if d.entry == mt5.DEAL_ENTRY_IN]
        out_deals = [d for d in d_list if d.entry == mt5.DEAL_ENTRY_OUT]
        if in_deals and out_deals:
            profit = sum(d.profit for d in out_deals)
            if profit < 0: closed_losing.append((pid, profit, out_deals[-1].time))
    if not closed_losing: return None
    closed_losing.sort(key=lambda x: x[2], reverse=True)
    return pos_deals[closed_losing[0][0]]

def analyze():
    deals = get_target_trade(1329003926)
    if not deals: return "No trade found"
    
    in_deals = [d for d in deals if d.entry == mt5.DEAL_ENTRY_IN]
    out_deals = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
    in_deal = in_deals[0]
    out_deal = out_deals[-1]
    symbol = in_deal.symbol
    entry_time = in_deal.time
    
    report = [f"Ticket: {in_deal.position_id}", f"Symbol: {symbol}"]
    report.append(f"Entry Time: {datetime.fromtimestamp(entry_time)}")
    report.append(f"Exit Time: {datetime.fromtimestamp(out_deal.time)}")
    report.append(f"Entry Price: {in_deal.price}")
    report.append(f"Exit Price: {out_deal.price}")
    report.append(f"Total Profit: {sum(d.profit for d in out_deals)}")
    report.append(f"Exit Reason/Comment: {out_deal.comment}")
    
    # Check ArcticDB
    try:
        store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
        lib = store["oracle_cache"]
        df = lib.read(f"{symbol}_meta").data
        df_sub = df[df["timestamp"] <= entry_time + 60]
        if not df_sub.empty:
            row = df_sub.iloc[-1]
            report.append("\n--- ARCTIC DB PRE-TRADE ---")
            for k in ['hmm_state', 'wasserstein_state', 'xgboost_prob', 'kronos_prob', 'faiss_similarity', 'sentiment_score', 'meta_conviction', 'atr']:
                report.append(f"{k}: {row.get(k, 'N/A')}")
    except Exception as e:
        report.append(f"Arctic Error: {e}")

    # Check logs for exact entry acceptance
    try:
        with open(r"C:\sentinel_logs\fastapi_sniper_v2.log", "r", encoding="utf-8") as f:
            fastapi = f.readlines()
            for line in fastapi[-10000:]:
                if str(in_deal.position_id) in line or "Received Signal" in line and symbol in line:
                    # just grab lines around entry time
                    try:
                        ts_str = line[:19]
                        log_time = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").timestamp()
                        if abs(log_time - entry_time) < 300:
                            report.append(f"FASTAPI: {line.strip()}")
                    except: pass
    except: pass
    
    with open(r"C:\Sentinel_Project\scratch\post_mortem_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report))

if __name__ == "__main__":
    analyze()
    mt5.shutdown()
