
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import gitagent_synthesis as syn
import gitagent_sigproc as sigproc
import gitagent_adaptive as adi
from gitagent_context_layer import UniversalContextLayer
import json
import os
from datetime import datetime, timezone

def run_weekly_audit():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    # Broad Watchlist for Weekly Forecast
    symbols = [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", 
        "NAS100", "SP500", "DJ30", "GER40", 
        "XAUUSD+", "XAGUSD", "CL-OIL", 
        "BTCUSD", "ETHUSD", "SOLUSD"
    ]

    print(f"\n=== SENTINEL WEEKLY HYBRID SCAN | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} EAT ===")
    
    audit_layer = UniversalContextLayer()
    recommendations = []

    for sym in symbols:
        # Fetch H1 for weekly bias
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 200)
        if rates is None or len(rates) < 100:
            continue
        
        df = pd.DataFrame(rates)
        price = df['close'].iloc[-1]
        
        # Module 10 Logic (Simplified for Scan)
        curr_trend = 1 if df['close'].rolling(50).mean().iloc[-1] > df['close'].rolling(200).mean().iloc[-1] else -1
        curr_smc = adi.get_smc_bias(df)
        curr_whale = adi.get_whale_bias(df)
        
        m10_score = 0
        if curr_trend == 1: m10_score += 2.0
        if curr_smc == 1: m10_score += 2.0
        if curr_whale == 1: m10_score += 1.5
        
        # Hybrid Audit for Weekly Outlook
        audit_data = {
            "symbol": sym,
            "regime": "WEEKLY_OUTLOOK_SCAN",
            "confidence": m10_score / 5.5,
            "cognition_factor": 0.7,
            "module_10": {"trend": curr_trend, "smc": curr_smc, "whale": curr_whale},
            "m10_score": m10_score
        }
        
        try:
            verdict, reasoning, engine = audit_layer.process(audit_data)
            results = {
                "symbol": sym,
                "price": price,
                "m10_score": m10_score,
                "verdict": verdict,
                "reasoning": reasoning,
                "engine": engine
            }
            recommendations.append(results)
            print(f"[{sym}] M10: {m10_score:.1f} | Verdict: {verdict} | {reasoning[:60]}...")
        except Exception as e:
            print(f"[{sym}] Audit Failed: {e}")

    # Output Rankings
    print("\n" + "="*50)
    print("TOP HYBRID PICKS FOR THE WEEK")
    print("="*50)
    
    # Sort by M10 score as base filter
    sorted_recs = sorted(recommendations, key=lambda x: x['m10_score'], reverse=True)
    for rec in sorted_recs[:5]:
        status = "🌟 STRONG BUY" if rec['verdict'] == "BUY" and rec['m10_score'] >= 4.0 else "👀 WATCH"
        print(f"{status} | {rec['symbol']} (${rec['price']:.5f})")
        print(f"  > Reasoning: {rec['reasoning']}")
        print("-" * 30)

    mt5.shutdown()

if __name__ == "__main__":
    run_weekly_audit()
