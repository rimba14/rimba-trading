import MetaTrader5 as mt5
import time

def close_by_ticket(ticket):
    pos = mt5.positions_get(ticket=ticket)
    if not pos: return False
    p = pos[0]
    from gitagent_action_layer import get_action_layer
    from gitagent_types import SmartTradeRequest
    al = get_action_layer()
    req = SmartTradeRequest(
        symbol=p.symbol,
        side=mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
        volume=p.volume,
        comment="Final Phase 84 Cleanup",
        position_ticket=p.ticket
    )
    res = al.execute_smart_trade(req)
    return res and res.retcode == mt5.TRADE_RETCODE_DONE


if mt5.initialize():
    pos_sol = mt5.positions_get(symbol='SOLUSD')
    if pos_sol:
        print(f"Found {len(pos_sol)} SOLUSD positions.")
        # Close all but the first one
        for p in pos_sol[1:]:
            success = close_by_ticket(p.ticket)
            print(f"Closing {p.ticket}: {success}")
    mt5.shutdown()
