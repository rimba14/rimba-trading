import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import gitagent_sigproc as sigproc
import gitagent_happo as happo
import gitagent_transformer as trans
import gitagent_microstructure as micro
import gitagent_synthesis as syn
from datetime import datetime, timezone

def diagnostic_probe():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    # 1. Check Limits
    account = mt5.account_info()
    positions = mt5.positions_get()
    directional_count = 0
    if positions:
        for p in positions:
            # Simple check for directional (same as engine)
            is_pair = False
            for pair in [["XAUUSD", "XAGUSD"], ["EURUSD", "GBPUSD"], ["NAS100", "SP500"]]:
                if p.symbol in pair: is_pair = True
            if not is_pair: directional_count += 1
    
    print(f"--- ACCOUNT DIAGNOSTIC ---")
    print(f"Equity: ${account.equity:.2f} | Balance: ${account.balance:.2f}")
    print(f"Active Positions: {len(positions) if positions else 0}")
    print(f"Directional Count: {directional_count} (Limit: 7)")
    print(f"Risk Cap: 10% (${account.balance * 0.1:.2f})")
    
    # 2. Check Top Symbols
    watchlist = ["EURUSD", "NAS100", "XAUUSD", "BTCUSD", "GBPUSD", "USDJPY"]
    print(f"\n--- SIGNAL DIAGNOSTIC (HAPPO v11.1) ---")
    
    for sym in watchlist:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 200)
        if rates is None: continue
        df = pd.DataFrame(rates)
        
        # Mocking the engine's signal assembly
        trans_score = trans.get_transformer_score(df.tail(100))
        lq_score = micro.get_microstructure_score(df)
        
        # HAPPO Observation
        happo_obs = {
            'trend': [0.5, 0.5, 1.0], # Dummy for speed
            'structure': [0.5, 0.0, 0.0],
            'flow': [0.5, 1.0, 1.0],
            'deep': [trans_score, (lq_score-50)/50.0],
            'macro': [0.0, 0.0, 0.0]
        }
        
        action, probs, contribs = happo.get_happo_action(happo_obs)
        action_name = {0: "HOLD", 1: "BUY", 2: "SELL"}[action]
        
        print(f"{sym}: {action_name} | Probs: {np.round(probs, 3)} | Trans: {trans_score:.2f} | Liquidity: {lq_score:.1f}")
        if action == 0:
            top_agent = max(contribs, key=contribs.get)
            print(f"  - Rejection: HOLD bias (Agent {top_agent} dominance)")

    mt5.shutdown()

if __name__ == "__main__":
    diagnostic_probe()
