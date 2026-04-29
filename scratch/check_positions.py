import MetaTrader5 as mt5
import json

def check_positions(symbol=None):
    if not mt5.initialize():
        print("FAIL")
        return
    
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if positions:
        results = [p._asdict() for p in positions]
        print(json.dumps(results, indent=2))
    else:
        print("[]")
    
    mt5.shutdown()

if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else None
    check_positions(sym)
