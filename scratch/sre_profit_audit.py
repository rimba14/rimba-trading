import MetaTrader5 as mt5
from arcticdb import Arctic
import pandas as pd
import time
from datetime import datetime, timezone

ARCTIC_DIR = "lmdb://C:/Sentinel_Project/data/arctic_cache"
SYMBOLS = ["LTCUSD", "ADAUSD", "XAGUSD"]

def audit_memory():
    if not mt5.initialize():
        print("FAILED MT5 init")
        return

    print("--- SRE DIAGNOSTIC: PROFIT MANAGER INTERNAL MEMORY AUDIT ---")
    
    try:
        store = Arctic(ARCTIC_DIR)
        lib = store["oracle_cache"]
    except Exception as e:
        print(f"FAILED ArcticDB connection: {e}")
        return

    for symbol in SYMBOLS:
        print(f"\n[ASSET: {symbol}]")
        
        # 1. Get Live Oracle Telemetry
        try:
            item = lib.read(f"{symbol}_meta")
            row = item.data.iloc[-1]
            conviction = float(row["meta_conviction"])
            atr = float(row["atr"])
            hmm_state = str(row["hmm_state"])
            ts_oracle = item.data.index[-1]
            if hasattr(ts_oracle, 'timestamp'):
                ts_val = ts_oracle.timestamp()
            else:
                ts_val = float(ts_oracle) / 1000 if ts_oracle > 1e12 else float(ts_oracle)
            
            print(f"  Oracle State: HMM={hmm_state} | P={conviction:.4f} | ATR={atr:.6f}")
            print(f"  Oracle Timestamp: {ts_oracle} (Staleness: {time.time() - ts_val:.1f}s)")
        except Exception as e:
            print(f"  FAILED to pull oracle data: {e}")
            continue

        # 2. Get MT5 Ticket Info
        pos = mt5.positions_get(symbol=symbol)
        if pos:
            p = pos[0]
            price_open = p.price_open
            # Calculate Virtual Stops (Logic from profit_manager.py line 309)
            # Assuming SL_ATR_MULT = 3.0 (Sentinel Standard) if not found
            sl_mult = 3.0 
            tp_mult = 6.0
            
            sl_level = price_open - (sl_mult * atr) if p.type == 0 else price_open + (sl_mult * atr)
            tp_level = price_open + (tp_mult * atr) if p.type == 0 else price_open - (tp_mult * atr)
            
            print(f"  Active Ticket: #{p.ticket} ({'BUY' if p.type==0 else 'SELL'})")
            print(f"  Entry Price: {price_open:.5f}")
            print(f"  Virtual SL: {sl_level:.5f}")
            print(f"  Virtual TP: {tp_level:.5f}")
            
            # Conviction Thresholds (from profit_manager.py line 250)
            threshold = 0.48 if p.type == 0 else 0.52
            print(f"  Meta-Conviction Threshold ($P$): {'<= 0.48' if p.type==0 else '>= 0.52'} (Current: {conviction:.4f})")
            
            # Telemetry Check
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                dt_tick = datetime.fromtimestamp(tick.time, tz=timezone.utc)
                print(f"  Live Price Feed: {tick.bid}/{tick.ask} | Last Updated: {dt_tick} ({time.time() - tick.time:.1f}s ago)")
            else:
                print("  Live Price Feed: OFFLINE")
        else:
            print("  Active Ticket: NONE FOUND")

    mt5.shutdown()

if __name__ == "__main__":
    audit_memory()
