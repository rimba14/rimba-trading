import MetaTrader5 as mt5
from gitagent_sor import get_sor_path
import gitagent_utils as utils
from dataclasses import dataclass
from typing import Optional

@dataclass
class TradeRequest:
    symbol: str
    order_type: int
    volume: float
    sl: float = 0.0
    tp: float = 0.0
    comment: str = "Agent15_SOR"
    position_ticket: Optional[int] = None

def execute_smart_order(req: TradeRequest):
    """
    Finds the best path and executes.
    Side: mt5.ORDER_TYPE_BUY or mt5.ORDER_TYPE_SELL
    """
    if not utils.is_market_open(req.symbol):
        print(f"[SOR] Skipping {req.symbol}: Market appears closed or inactive.")
        return MockResult(mt5.TRADE_RETCODE_REJECT, "Market Closed")

    is_synth, path, cost, direct_cost = get_sor_path(req.symbol, req.order_type)
    
    norm_vol = utils.normalize_volume(req.symbol, req.volume)
    if norm_vol <= 0:
        return MockResult(mt5.TRADE_RETCODE_REJECT, "Zero Normalized Volume")

    if not is_synth:
        # Just execute direct
        direct_req = TradeRequest(
            symbol=req.symbol,
            order_type=req.order_type,
            volume=norm_vol,
            sl=req.sl,
            tp=req.tp,
            comment=req.comment,
            position_ticket=req.position_ticket
        )
        return execute_standard_order(direct_req)
    
    # Execute Synthetic
    print(f"[SOR] Synthetic Path Chosen for {req.symbol}: {path} (Cost {cost} vs {direct_cost})")
    results = []
    for leg_symbol, leg_side in path:
        # Note: Position ticket generally only applies to direct closures of specific tickets
        leg_req = TradeRequest(
            symbol=leg_symbol,
            order_type=leg_side,
            volume=norm_vol,
            sl=0,
            tp=0,
            comment=req.comment + "_leg",
            position_ticket=req.position_ticket
        )
        res = execute_standard_order(leg_req)
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

def execute_standard_order(req: TradeRequest):

    if not utils.is_market_open(req.symbol):
        print(f"[SOR_EXEC] Skipping Leg {req.symbol}: Market Closed")
        return MockResult(mt5.TRADE_RETCODE_REJECT, "Market Closed")
        
    tick = utils.mt5.symbol_info_tick(req.symbol)
    if not tick:
        print(f"[SOR_ERR] No tick for {req.symbol}. Leg execution aborted.")
        return MockResult(mt5.TRADE_RETCODE_REJECT, "No Tick")
        
    # Handle Limit Orders
    action_type = mt5.TRADE_ACTION_DEAL
    order_type = req.order_type
    
    if req.order_type in [mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT]:
        action_type = mt5.TRADE_ACTION_PENDING

    price = tick.ask if req.order_type == mt5.ORDER_TYPE_BUY else tick.bid

    request = {
        "action": action_type,
        "symbol": req.symbol,
        "volume": float(req.volume),
        "type": order_type,
        "price": float(price),
        "sl": float(req.sl),
        "tp": float(req.tp),
        "magic": 123456,
        "comment": str(req.comment)[:15] if req.comment else "",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC if action_type == mt5.TRADE_ACTION_DEAL else mt5.ORDER_FILLING_RETURN,
    }
    
    # CRITICAL: Include position ticket for Hedging account closures/modifications
    if req.position_ticket:
        request["position"] = int(req.position_ticket)
        
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        msg = result.comment if result else "Timeout"
        err_code = mt5.last_error()
        print(f"[SOR_EXEC] FAILED {req.symbol} | RetCode: {result.retcode if result else 'N/A'} | Msg: {msg} | MT5_Err: {err_code}")
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
