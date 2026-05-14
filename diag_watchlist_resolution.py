import MetaTrader5 as mt5
import logging

logging.basicConfig(level=logging.INFO)

def get_valid_mt5_symbol(base_symbol: str) -> str | None:
    info = mt5.symbol_info(base_symbol)
    if info and info.visible:
        return base_symbol

    for suffix in (".m", ".pro", ".t", "+", "-", ".r", ".c", ".x"):
        test_sym = f"{base_symbol}{suffix}"
        info = mt5.symbol_info(test_sym)
        if info and info.visible:
            return test_sym
    
    all_symbols = mt5.symbols_get()
    if all_symbols:
        base_up = base_symbol.upper()
        for s in all_symbols:
            if s.name.upper() == base_up: return s.name
            if s.name.upper().startswith(base_up) and len(s.name) <= len(base_symbol) + 5: return s.name
            if base_up in s.name.upper(): return s.name
    return None

BASE_WATCHLIST = [
    "BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "LTCUSD", "BCHUSD", "XRPUSD", "ADAUSD", "DOTUSD",
    "MATICUSD", "DOGEUSD", "UNIUSD", "ATOMUSD", "TRXUSD",
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "NZDUSD", "USDCAD", "EURGBP", "EURJPY", "GBPJPY",
    "EURCHF", "AUDJPY", "NZDJPY", "CHFJPY", "EURAUD", "GBPAUD", "USDMXN", "USDZAR", "USDTRY", "EURNOK",
    "EURSEK", "USDCNH", "USDSGD", "USDHKD", "EURPLN",
    "SP500", "NAS100", "US30", "GER40", "HK50", "US2000", "FRA40", "XAUUSD", "XAGUSD", "CL-OIL"
]

if not mt5.initialize():
    print("MT5 Init Failed")
else:
    resolved = []
    failed = []
    for sym in BASE_WATCHLIST:
        v = get_valid_mt5_symbol(sym)
        if v:
            resolved.append(v)
        else:
            failed.append(sym)
    
    print(f"Resolved: {len(resolved)}")
    print(f"Failed: {len(failed)}")
    print(f"Failed symbols: {failed}")
    
    # Try to find suggestions for failed
    all_syms = [s.name for s in mt5.symbols_get()]
    for f in failed:
        matches = [s for s in all_syms if f in s]
        print(f"Suggestions for {f}: {matches[:5]}")
    
    mt5.shutdown()
