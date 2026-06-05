import json
import MetaTrader5 as mt5
from arcticdb import Arctic

ARCTIC_DIR = "lmdb://C:/Sentinel_Project/data/arctic_cache"

def get_open_symbols():
    if not mt5.initialize():
        print("MT5 initialize failed")
        return set()
    positions = mt5.positions_get()
    if positions is None:
        return set()
    return set(p.symbol for p in positions)

def extract_signals():
    open_symbols = get_open_symbols()
    
    try:
        store = Arctic(ARCTIC_DIR)
        lib = store["oracle_cache"]
        symbols = [sym.replace("_meta", "") for sym in lib.list_symbols() if sym.endswith("_meta")]
    except Exception as e:
        print(f"Failed to read arctic: {e}")
        symbols = []

    valid_signals = []
    
    for symbol in symbols:
        if symbol in open_symbols:
            continue
            
        try:
            item = lib.read(f"{symbol}_meta")
            df = item.data
            if df.empty:
                continue
                
            row = df.iloc[-1]
            p_blend = float(row.get("meta_conviction", 0.0))
            
            # v30.50 constraints
            if p_blend >= 0.82:
                # Mocking activity ratio and OFI CP since they might not be in meta
                activity_ratio = float(row.get("activity_ratio", 0.0))
                ofi_cp = float(row.get("ofi_cp_prob", 0.0))
                
                if activity_ratio >= 1.5 and ofi_cp >= 0.95:
                    valid_signals.append({
                        "symbol": symbol,
                        "p_blend": p_blend,
                        "activity_ratio": activity_ratio,
                        "ofi_cp": ofi_cp,
                        "hmm_state": row.get("hmm_state", "NEUTRAL")
                    })
        except Exception as e:
            pass

    return valid_signals

if __name__ == "__main__":
    signals = extract_signals()
    if len(signals) < 4:
        print("INSUFFICIENT CONVICTION FOR 4 SLOTS.")
    else:
        # Sort by conviction
        signals.sort(key=lambda x: x["p_blend"], reverse=True)
        top_4 = signals[:4]
        print(json.dumps(top_4, indent=2))
