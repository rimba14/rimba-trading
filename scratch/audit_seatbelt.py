import sys
import os
sys.path.append(r"C:\Sentinel_Project")
import MetaTrader5 as mt5
import git_arctic
import gitagent_utils as utils

def get_asset_multiplier(symbol):
    regime = utils.get_symbol_regime(symbol)
    if regime == "FOREX_USD" or regime == "FOREX_CROSS": return 6.0
    elif regime in ["INDEX", "COMMODITY", "CRYPTO"]: return 4.0
    elif regime == "EQUITY": return 3.0
    return 4.0

if not mt5.initialize():
    print("MT5 Init Failed")
    sys.exit()

store = git_arctic.get_arctic()
lib = store['oracle_cache']
orders = mt5.orders_get()
if not orders:
    print("No pending orders found.")
    sys.exit()

print(f"{'SYMBOL':<10} | {'TICKET':<10} | {'SL_DIST':<10} | {'CAT_REQ':<10} | {'STATUS'}")
print("-" * 60)

for o in orders:
    if o.magic != 142: continue
    
    try:
        k_item = lib.read(f"{o.symbol}_kronos")
        base_atr = float(k_item.data.iloc[-1].get('base_atr', 0.0))
        mult = get_asset_multiplier(o.symbol)
        cat_dist = base_atr * mult * 2.0
        
        sl_dist = abs(o.price_open - o.sl) if o.sl != 0 else 0
        status = "OK" if sl_dist >= cat_dist * 0.95 else "BREACH (Too Tight)"
        if o.sl == 0: status = "MISSING_SL"
        
        print(f"{o.symbol:<10} | {o.ticket:<10} | {sl_dist:<10.5f} | {cat_dist:<10.5f} | {status}")
    except Exception as e:
        print(f"Error for {o.symbol}: {e}")

mt5.shutdown()
