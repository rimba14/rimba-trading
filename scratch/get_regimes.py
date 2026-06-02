from arcticdb import Arctic
import pandas as pd
import sys

def main():
    try:
        store = Arctic('lmdb://C:/Sentinel_Project/data/arctic_cache')
        lib = store['oracle_cache']
    except Exception as e:
        print('Failed to open database cache:', e)
        sys.exit(1)

    regime_counts = {}
    crisis_assets = []
    stagnant_assets = []
    pristine_assets = []

    for sym in lib.list_symbols():
        if sym.endswith('_meta'):
            base_sym = sym.replace('_meta', '')
            try:
                data = lib.read(sym).data
                if not data.empty:
                    row = data.iloc[-1]
                    regime = row.get('wasserstein_state', row.get('hmm_state', 'UNKNOWN'))
                    p_val = float(row.get('meta_conviction', row.get('xgb_p', 0.5)))
                    
                    regime_counts[regime] = regime_counts.get(regime, 0) + 1
                    
                    item = {
                        'symbol': base_sym,
                        'regime': regime,
                        'conviction': p_val,
                        'entropy': row.get('entropy', 0.0)
                    }
                    
                    if any(x in regime for x in ['CRISIS', 'PANIC', 'TAIL']):
                        crisis_assets.append(item)
                    elif any(x in regime for x in ['STAGNANT', 'CLOSED']):
                        stagnant_assets.append(item)
                    else:
                        pristine_assets.append(item)
            except Exception as ex:
                print(f"Error reading {sym}: {ex}")

    print('=== REGIME DISTRIBUTION ===')
    for k, v in regime_counts.items():
        print(f'{k}: {v}')

    print('\n=== CRISIS TAIL / VOLATILE ASSETS ===')
    if crisis_assets:
        for a in sorted(crisis_assets, key=lambda x: x['symbol']):
            print(f"{a['symbol']}: Regime={a['regime']}, Conviction={a['conviction']:.3f}")
    else:
        print('None. No assets are in crisis tail.')

    print('\n=== STAGNANT / CLOSED ASSETS ===')
    if stagnant_assets:
        print(', '.join(sorted([a['symbol'] for a in stagnant_assets])))

    print('\n=== PRISTINE / ACTIVE TRADING ASSETS ===')
    if pristine_assets:
        for a in sorted(pristine_assets, key=lambda x: abs(x['conviction'] - 0.5), reverse=True)[:15]:
            print(f"{a['symbol']}: Regime={a['regime']}, Conviction={a['conviction']:.3f}")

if __name__ == "__main__":
    main()
