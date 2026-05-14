import MetaTrader5 as mt5
from datetime import datetime

def audit_tickets(tickets):
    if not mt5.initialize():
        print("MT5 Init Failed")
        return
    
    results = []
    for t in tickets:
        deals = mt5.history_deals_get(position=t)
        if deals:
            deal_list = []
            for d in deals:
                deal_list.append({
                    'ticket': d.ticket,
                    'symbol': d.symbol,
                    'profit': d.profit,
                    'time': datetime.fromtimestamp(d.time).isoformat(),
                    'comment': d.comment,
                    'entry': d.entry,
                    'reason': d.reason
                })
            results.append({'pos_id': t, 'status': 'closed' if any(d.entry == 1 for d in deals) else 'open', 'deals': deal_list})
        else:
            # Check if it's currently open
            positions = mt5.positions_get(ticket=t)
            if positions:
                p = positions[0]
                results.append({'pos_id': t, 'status': 'open', 'symbol': p.symbol, 'profit': p.profit, 'comment': p.comment})
            else:
                results.append({'pos_id': t, 'status': 'not_found'})
    
    import json
    print(json.dumps(results, indent=2))
    mt5.shutdown()

if __name__ == "__main__":
    audit_tickets([1301723241, 1300830944, 1301105639, 1300636089, 1302082320])
