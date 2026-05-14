import MetaTrader5 as mt5
import time
import math
import logging

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [REANCHOR] %(message)s')
logger = logging.getLogger("ReAnchor")

def calculate_atr(symbol, timeframe=mt5.TIMEFRAME_H1, count=20):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return 0.001 
    atr = sum([r['high'] - r['low'] for r in rates]) / len(rates)
    return atr

def reanchor_positions():
    if not mt5.initialize():
        logger.error("MT5 Init Failed")
        return

    positions = mt5.positions_get()
    if not positions:
        logger.info("No active positions found.")
        return

    for pos in positions:
        if pos.sl == 0.0 or pos.tp == 0.0:
            logger.info(f"Position {pos.symbol} (Ticket: {pos.ticket}) is missing SL/TP. Re-anchoring...")
            
            info = mt5.symbol_info(pos.symbol)
            if not info: continue
            
            tick = mt5.symbol_info_tick(pos.symbol)
            if not tick: continue

            current_atr = calculate_atr(pos.symbol)
            current_spread = abs(tick.ask - tick.bid)
            
            # Spread-Aware Floor
            # In high-spread assets (like EURNOK), stoplevels are often tied to spread
            safety_scalar = max(current_atr, current_spread)
            
            sl_dist = 2.5 * safety_scalar
            tp_dist = 5.0 * safety_scalar
            
            if pos.type == mt5.ORDER_TYPE_BUY:
                new_sl = tick.bid - sl_dist
                new_tp = tick.ask + tp_dist
            else:
                new_sl = tick.ask + sl_dist
                new_tp = tick.bid - tp_dist
                
            # Normalization
            tick_size = info.trade_tick_size
            if tick_size > 0:
                new_tp = round(new_tp / tick_size) * tick_size
                new_sl = round(new_sl / tick_size) * tick_size
            
            new_sl = round(new_sl, info.digits)
            new_tp = round(new_tp, info.digits)
            
            logger.info(f"[{pos.symbol}] Requesting SL: {new_sl} | TP: {new_tp} | Spread: {current_spread:.5f} | ATR: {current_atr:.5f}")
            
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "position": pos.ticket,
                "sl": new_sl,
                "tp": new_tp
            }
            
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Successfully re-anchored {pos.symbol} (#{pos.ticket})")
            else:
                logger.error(f"❌ Failed to re-anchor {pos.symbol} (#{pos.ticket}) | Retcode: {result.retcode if result else 'None'} | Comment: {result.comment if result else 'N/A'}")

    mt5.shutdown()

if __name__ == "__main__":
    reanchor_positions()
