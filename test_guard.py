import MetaTrader5 as mt5

def test_duplicate_guard(test_sym):
    if not mt5.initialize():
        print("Init failed")
        return

    positions = mt5.positions_get()
    print(f"Current Positions: {[p.symbol for p in positions]}")
    
    # Simulate the guard logic from vantage_execute.py
    is_duplicate = False
    for p in positions:
        if p.symbol == test_sym:
            print(f"[DUPLICATE_GUARD] {test_sym} already held. Skipping.")
            is_duplicate = True
            break
            
    if not is_duplicate:
        print(f"[GUARD_FAIL] {test_sym} NOT found in open positions. Bot would fire.")

if __name__ == "__main__":
    # Test with EURSEK and any likely suffixes
    for sym in ["EURSEK", "EURSEK+", "EURSEK.r"]:
        print(f"\nTesting Guard for: {sym}")
        test_duplicate_guard(sym)
