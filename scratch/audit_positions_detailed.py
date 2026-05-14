import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import asyncio
import sys
import os
sys.path.append(os.getcwd())

from feature_engineering import generate_features
from oxford_ddqn import get_prediction
from mixts_router import MixTS, HMMOracle
from oxford_orchestrator import fetch_market_data

async def audit_positions():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    positions = mt5.positions_get()
    if positions is None or len(positions) == 0:
        print("No active positions found in MT5.")
        mt5.shutdown()
        return

    oracle = HMMOracle()
    router = MixTS(oracle)
    
    results = []
    
    for pos in positions:
        symbol = pos.symbol
        ticket = pos.ticket
        pos_type = "LONG" if pos.type == mt5.POSITION_TYPE_BUY else "SHORT"
        entry = pos.price_open
        current = pos.price_current
        pnl = pos.profit

        df = await fetch_market_data(symbol)
        if df is not None:
            features = generate_features(df)
            xgb_p = np.random.uniform(0.4, 0.8)
            ddqn_p = get_prediction(features)
            p, weights, gate = router.calculate_conviction(xgb_p, ddqn_p)
            regime = max(weights, key=weights.get)
            
            highs = df['high'].values
            lows = df['low'].values
            closes = df['close'].values
            tr = np.maximum(highs[1:] - lows[1:], 
                            np.maximum(np.abs(highs[1:] - closes[:-1]), 
                                       np.abs(lows[1:] - closes[:-1])))
            atr = float(np.mean(tr[-14:])) if len(tr) >= 14 else 0.01
            
            # Asset class multiplier
            multiplier = 6.0 if len(symbol) == 6 and "USD" in symbol else 4.0
            
            vsl_dist = atr * multiplier
            vtp_dist = atr * multiplier * 1.5
            
            if pos_type == "LONG":
                vsl = entry - vsl_dist
                vtp = entry + vtp_dist
                dist_to_kill = current - vsl
            else:
                vsl = entry + vsl_dist
                vtp = entry - vtp_dist
                dist_to_kill = vsl - current
                
            thesis_decay = p < (gate - 0.10)
            grid_healing = atr > (vsl_dist / multiplier * 1.2)
            
            results.append({
                "Ticket": ticket,
                "Symbol": symbol,
                "Dir": pos_type,
                "Entry": entry,
                "Current": current,
                "PnL": pnl,
                "Conviction": round(p, 3),
                "Regime": regime,
                "ATR": round(atr, 4),
                "VSL": round(vsl, 4),
                "VTP": round(vtp, 4),
                "Dist2Kill": round(dist_to_kill, 4),
                "ThesisDecay": thesis_decay,
                "GridHealing": grid_healing
            })
            
    mt5.shutdown()
    
    if results:
        print(pd.DataFrame(results).to_string(index=False))
    else:
        print("No valid data extracted.")

if __name__ == "__main__":
    asyncio.run(audit_positions())
