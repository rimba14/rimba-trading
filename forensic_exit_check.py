import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
import time
from vantage_execute import SentinelConductor

def run_forensic_check(symbols):
    conductor = SentinelConductor()
    results = {}
    
    # Load latest cognition factor
    cognition_factor = 0.0
    try:
        with open("C:\\Sentinel_Project\\cognition_bridge.json", "r") as f:
            cdata = json.load(f)
            cognition_factor = cdata.get('cognition_factor', 0.0)
    except:
        pass

    for sym in symbols:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 256)
        if rates is None:
            results[sym] = "No data"
            continue
        
        df = pd.DataFrame(rates)
        action_receipt, context_receipt = conductor.run_one_cycle(sym, df, cognition_factor)
        
        results[sym] = {
            "verdict": action_receipt['action'],
            "cognition": context_receipt['cognition_factor'],
            "history": context_receipt['history_summary'],
            "inconsistent": context_receipt['is_inconsistent'],
            "current_price": float(df['close'].iloc[-1])
        }
    
    return results

if __name__ == "__main__":
    if not mt5.initialize():
        print("MT5 Init Failed")
    else:
        syms = ["USDJPY", "GBPUSD"]
        audit = run_forensic_check(syms)
        print(json.dumps(audit, indent=2))
        mt5.shutdown()
