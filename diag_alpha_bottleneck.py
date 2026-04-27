import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import sys
import os

# Ensure local imports work
sys.path.append('C:\\Sentinel_Project\\')

import alpha_combiner
import gitagent_sigproc as sigproc
import gitagent_utils as utils
import vantage_execute as ve
from vantage_execute import SentinelConductor, calculate_atr

def diag_bottleneck():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    conductor = SentinelConductor()
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "NAS100", "BTCUSD", "ETHUSD", "XRPUSD", "SP500", "UK100"]
    
    raw_signals = {}
    vols = {}
    metadata = {}

    print(f"\n[DIAG] Auditing {len(symbols)} symbols for Alpha Bottlenecks...")
    print("-" * 80)
    print(f"{'SYMBOL':<10} | {'TRANS_VERDICT':<10} | {'RAW_SCORES':<20}")
    
    for sym in symbols:
        try:
            mt5.symbol_select(sym, True)
            rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 100)
            if rates is None or len(rates) < 50: continue
            
            df = pd.DataFrame(rates)
            # 1. Perception Layer
            p_res = conductor.perception.process(df)
            # 2. Representation
            r_res = conductor.representation.process(p_res)
            # 3. Cognition (Transformer)
            c_res = conductor.cognition.process(r_res)
            
            # Extract scores even if it's "NONE"
            scores = c_res.get('agent_scores', {})
            if not scores:
                # Production Fallback Logic (sync with vantage_execute.py)
                r = ve.rsi(df['close'], 14).iloc[-1]
                scores = {
                    "MeanRev": (r-50)/50.0,
                    "SMC": ve.adi.get_smc_bias(df),
                    "WHL": ve.adi.get_whale_bias(df),
                    "Trend": 1.0 if df['close'].iloc[-1] > df['close'].rolling(50).mean().iloc[-1] else -1.0
                }
            
            verdict = c_res.get('action', 'NONE')
            print(f"{sym:<10} | {verdict:<13} | {str({k: round(v,3) for k,v in scores.items()}):<20}")
            
            raw_signals[sym] = scores
            vols[sym] = ve.calculate_atr(df)
            metadata[sym] = verdict
            
        except Exception as e:
            print(f"{sym:<10} | ERROR: {e}")

    print("-" * 80)
    print(f"\n[DIAG] Running Alpha Combiner (Residual Extraction)...")
    
    combined = alpha_combiner.combiner.process_signals(raw_signals, vols)
    
    print("-" * 80)
    print(f"{'SYMBOL':<10} | {'TRANS_VERDICT':<10} | {'RESIDUAL_ALPHA':<15} | {'NORM_SCORE (x10)':<15}")
    
    for sym, weight in combined.items():
        norm_score = abs(weight) * 10.0
        print(f"{sym:<10} | {metadata[sym]:<13} | {weight:>14.4f} | {norm_score:>14.4f}")

    print("-" * 80)
    print("[DIAG] ANALYSIS COMPLETE.")

if __name__ == "__main__":
    diag_bottleneck()
