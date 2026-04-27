import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import gitagent_sigproc as sigproc
import gitagent_happo as happo
import gitagent_transformer as trans
import gitagent_microstructure as micro
import gitagent_lob as lob

def market_scan_probe():
    if not mt5.initialize(): return
    
    symbols = [
        "NAS100", "SP500", "DJ30", "XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD",
        "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "NVDA", "AAPL", "MSFT", "TSLA"
    ]
    
    results = []
    print(f"--- HAPPO v11.1 NY PRE-MARKET SCAN ---")
    
    for sym in symbols:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 200)
        if rates is None: continue
        df = pd.DataFrame(rates)
        
        # 1. Component Signals
        trans_score = trans.get_transformer_score(df.tail(100))
        lq_score = micro.get_microstructure_score(df)
        smc_score = 1.0 if df['close'].iloc[-1] > df['close'].rolling(50).mean().iloc[-1] else -1.0
        
        # 2. HAPPO Inference
        lob_data = lob.get_lob_analytics(sym)
        l1_imbalance = lob_data.get('l1_imbalance', 0.0)

        happo_obs = {
            'trend':     [smc_score, 0.5, 1.0],
            'structure': [0.5, 0.0, 0.0],
            'flow':      [0.5, 1.0, 1.0],
            'deep':      [trans_score, (lq_score-50)/50.0, l1_imbalance],
            'macro':     [0.0, 0.0, 0.0]
        }
        
        action, probs, _ = happo.get_happo_action(happo_obs)
        conviction = max(probs) - (1/3.0) # Delta from uniform
        
        results.append({
            "sym": sym, "action": action, "prob": max(probs), "conviction": conviction,
            "trans": trans_score, "lq": lq_score
        })

    # Sort by conviction delta
    top = sorted(results, key=lambda x: x['conviction'], reverse=True)
    for r in top[:8]:
        act = {0: "HOLD", 1: "BUY", 2: "SELL"}[r['action']]
        print(f"{r['sym']}: {act:4} | Confidence: {r['prob']:.1%} | Conviction Delta: {r['conviction']:.3f} | Trans: {r['trans']:.2f}")

if __name__ == "__main__":
    market_scan_probe()
