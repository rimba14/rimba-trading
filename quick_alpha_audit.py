import sys
import os
import json
import time

# Mocking some globals required by vantage_execute imports if they fail
os.environ['PATH'] += os.pathsep + 'C:\\Sentinel_Project\\'
sys.path.append('C:\\Sentinel_Project\\')

import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# Import the core engine components
import gitagent_synthesis as syn
import gitagent_utils as utils
from vantage_execute import SentinelConductor

def audit_priority_watchlist():
    if not mt5.initialize():
        print("MT5 Init failed")
        return

    targets = ['EURNOK', 'USDZAR', 'EURUSD', 'BTCUSD', 'NAS100', 'XRPUSD', 'BNBUSD']
    print(f"\n[*] INSTITUTIONAL ALPHA AUDIT (PERCEPTION LAYER v12.8)")
    print("-" * 65)
    
    conductor = SentinelConductor()
    cognition_factor = 0.4 # Baseline
    
    for sym in targets:
        try:
            mt5.symbol_select(sym, True)
            rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 100)
            if rates is None or len(rates) < 50:
                print(f"SYMBOL: {sym:<10} | ERROR: Insufficient data")
                continue
            
            df = pd.DataFrame(rates)
            c_res = conductor.run_to_cognition(df, cognition_factor)
            
            score = c_res.get('monolithic_score', 0.0)
            agent_scores = c_res.get('agent_scores', {})
            verdict = "BUY" if score > 5.1 else ("SELL" if score < -5.1 else "NONE")
            
            print(f"SYMBOL: {sym:<10} | Score: {score:>7.2f} | Verdict: {verdict:<5}")
            if agent_scores:
                top_agents = sorted(agent_scores.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
                print(f"   [TOP_AGENTS] {top_agents}")
        except Exception as e:
            print(f"SYMBOL: {sym:<10} | ERROR: {e}")
    
    print("-" * 65)
    
    # Check Risk Capacity
    account = mt5.account_info()
    if account:
        equity = account.equity
        positions = mt5.positions_get()
        nominal = sum([p.volume * p.price_open for p in positions]) if positions else 0
        risk_pct = (nominal / equity) * 100 if equity > 0 else 0
        print(f"PORTFOLIO: Equity: ${equity:.2f} | Nominal Exp: ${nominal:.2f} | Heat: {risk_pct:.1f}%")
        if risk_pct > 12:
            print("STATUS: !!! RISK SATURATED (CAP: 12%) !!! No new entries allowed.")
        else:
            print(f"STATUS: Capacity available ({12.0 - risk_pct:.1f}% risk budget remaining).")

if __name__ == "__main__":
    audit_priority_watchlist()
