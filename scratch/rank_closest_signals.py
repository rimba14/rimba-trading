import json
from pathlib import Path
from datetime import datetime

def main():
    path = Path('c:/Sentinel_Project/data/p_score_history.jsonl')
    if not path.exists():
        print('No data file found.')
        return

    lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
    if not lines:
        print('Data file is empty.')
        return

    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except Exception:
            pass

    # Group by symbol, taking the latest record for each
    latest_by_symbol = {}
    for r in records:
        sym = r['symbol']
        if sym not in latest_by_symbol or r['timestamp'] > latest_by_symbol[sym]['timestamp']:
            latest_by_symbol[sym] = r

    results = []
    for sym, r in latest_by_symbol.items():
        p = r['p_score']
        state = r.get('hmm_state', 'UNKNOWN')
        
        # Calculate proximity
        if p >= 0.50:
            direction = 'BUY'
            target = 0.60
            distance = max(0.0, target - p)
        else:
            direction = 'SELL'
            target = 0.40
            distance = max(0.0, p - target)
            
        results.append({
            'symbol': sym,
            'p_score': p,
            'direction': direction,
            'state': state,
            'distance': distance,
            'timestamp': datetime.fromtimestamp(r['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        })

    # Sort by distance ascending (smallest distance first means closest to firing)
    results.sort(key=lambda x: x['distance'])

    print('| Rank | Symbol | Direction | HMM State | P-Score | Distance to Fire | Last Evaluated |')
    print('|---|---|---|---|---|---|---|')
    for idx, res in enumerate(results[:20], 1):
        status = '**READY / FIRING**' if res['distance'] == 0.0 else f'{res["distance"]:.4f}'
        print(f"| {idx} | {res['symbol']} | {res['direction']} | {res['state']} | {res['p_score']:.4f} | {status} | {res['timestamp']} |")

if __name__ == '__main__':
    main()
