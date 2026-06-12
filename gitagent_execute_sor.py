import MetaTrader5 as mt5
from gitagent_sor import get_sor_path
import gitagent_utils as utils
from gitagent_types import StandardOrder

def execute_smart_order(symbol, side, volume, sl=0, tp=0, comment="Agent15_SOR", position_ticket=None):
    """
    Finds the best path and executes.
    Side: mt5.ORDER_TYPE_BUY or mt5.ORDER_TYPE_SELL
    """
    if not utils.is_market_open(symbol):
        print(f"[SOR] Skipping {symbol}: Market appears closed or inactive.")
        return MockResult(mt5.TRADE_RETCODE_REJECT, "Market Closed")

    is_synth, path, cost, direct_cost = get_sor_path(symbol, side)
    
    norm_vol = utils.normalize_volume(symbol, volume)
    if norm_vol <= 0:
        return MockResult(mt5.TRADE_RETCODE_REJECT, "Zero Normalized Volume")

    if not is_synth:
        # Just execute direct
        order = StandardOrder(
            symbol=symbol,
            order_type=side,
            volume=norm_vol,
            sl=sl,
            tp=tp,
            comment=comment,
            position_ticket=position_ticket
        )
        return execute_standard_order(order)
    
    # Execute Synthetic
    print(f"[SOR] Synthetic Path Chosen for {symbol}: {path} (Cost {cost} vs {direct_cost})")
    results = []
    for leg_symbol, leg_side in path:
        # Note: Position ticket generally only applies to direct closures of specific tickets
        order = StandardOrder(
            symbol=leg_symbol,
            order_type=leg_side,
            volume=norm_vol,
            sl=0,
            tp=0,
            comment=comment + "_leg",
            position_ticket=position_ticket
        )
        res = execute_standard_order(order)
        results.append(res)
    
    return results

class MockResult:
    def __init__(self, retcode, comment):
        self.retcode = retcode
        self.comment = comment
        self.order = 0

def modify_standard_sltp(symbol, ticket, sl, tp):
    """Updates SL/TP for an existing position."""
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": int(ticket),
        "sl": float(sl),
        "tp": float(tp),
        "magic": 123456
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        msg = result.comment if result else "Timeout"
        print(f"[SOR_MOD] FAILED {symbol} | Ticket: {ticket} | Msg: {msg}")
    return result

def execute_standard_order(order: StandardOrder):

    if not utils.is_market_open(order.symbol):
        print(f"[SOR_EXEC] Skipping Leg {order.symbol}: Market Closed")
        return MockResult(mt5.TRADE_RETCODE_REJECT, "Market Closed")
        
    tick = utils.mt5.symbol_info_tick(order.symbol)
    if not tick:
        print(f"[SOR_ERR] No tick for {order.symbol}. Leg execution aborted.")
        return MockResult(mt5.TRADE_RETCODE_REJECT, "No Tick")
        
    # Handle Limit Orders
    action_type = mt5.TRADE_ACTION_DEAL
    order_type = order.order_type
    
    if order_type in [mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT]:
        action_type = mt5.TRADE_ACTION_PENDING

    if order.price is not None:
        price = order.price
    else:
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

    request = {
        "action": action_type,
        "symbol": order.symbol,
        "volume": float(order.volume),
        "type": order_type,
        "price": float(price),
        "sl": float(order.sl),
        "tp": float(order.tp),
        "magic": 123456,
        "comment": str(order.comment)[:15] if order.comment else "",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC if action_type == mt5.TRADE_ACTION_DEAL else mt5.ORDER_FILLING_RETURN,
    }
    
    # CRITICAL: Include position ticket for Hedging account closures/modifications
    if order.position_ticket:
        request["position"] = int(order.position_ticket)
        
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        msg = result.comment if result else "Timeout"
        err_code = mt5.last_error()
        print(f"[SOR_EXEC] FAILED {symbol} | RetCode: {result.retcode if result else 'N/A'} | Msg: {msg} | MT5_Err: {err_code}")
        if result:
            print(f" -> Result Dump: {result._asdict()}")
        return result if result else MockResult(mt5.TRADE_RETCODE_ERROR, "Timeout")
    return result

def close_position(symbol, ticket, comment="Agent_Close"):
    """Institutional close: opposite trade for hedging/netting."""
    pos = mt5.positions_get(ticket=ticket)
    if not pos: return None
    p = pos[0]
    
    # Invert type
    close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(symbol)
    if not tick: return None
    price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(p.volume),
        "type": close_type,
        "position": int(ticket),
        "price": float(price),
        "magic": 123456,
        "comment": str(comment)[:15],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    return mt5.order_send(request)

def close_partial(symbol, ticket, volume, comment="Agent_Partial"):
    """Institutional partial close."""
    pos = mt5.positions_get(ticket=ticket)
    if not pos: return None
    p = pos[0]
    
    # Ensure volume doesn't exceed current
    final_vol = min(volume, p.volume)
    if final_vol < 0.01: return None

    close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(symbol)
    if not tick: return None
    price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(final_vol),
        "type": close_type,
        "position": int(ticket),
        "price": float(price),
        "magic": 123456,
        "comment": str(comment)[:15],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    return mt5.order_send(request)
