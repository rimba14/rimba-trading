import MetaTrader5 as mt5
import math
import logging
from fastapi_sniper import calculate_structural_atr_d1

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("Reanchor")

def _get_asset_multiplier(sym):
    sym_upper = sym.upper()
    if 'BTC' in sym_upper or 'ETH' in sym_upper: return 4.0
    if 'US30' in sym_upper or 'NAS100' in sym_upper or 'US2000' in sym_upper or 'SPX500' in sym_upper: return 4.0
    if 'XAU' in sym_upper or 'XAG' in sym_upper: return 4.0
    return 6.0

def reanchor_positions():
    if not mt5.initialize():
        logger.error("MT5 initialization failed")
        return

    positions = mt5.positions_get()
    if not positions:
        logger.info("No open positions found.")
        mt5.shutdown()
        return

    for pos in positions:
        symbol = pos.symbol
        ticket = pos.ticket
        entry_price = pos.price_open
        direction = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        
        info = mt5.symbol_info(symbol)
        if not info:
            logger.warning(f"[{symbol}] Could not get symbol info.")
            continue
            
        digits = info.digits

        # 1. Get D1 Structural ATR
        d1_atr = calculate_structural_atr_d1(symbol, period=14)
        if d1_atr <= 0:
            logger.warning(f"[{symbol}] Invalid D1 ATR. Skipping.")
            continue

        # 2. Calculate Final SL
        multiplier = _get_asset_multiplier(symbol)
        calculated_sl_dist = d1_atr * multiplier
        broker_minimum_sl = info.trade_stops_level * info.point
        final_sl_dist = max(calculated_sl_dist, broker_minimum_sl)

        sl_price = entry_price - final_sl_dist if direction == "BUY" else entry_price + final_sl_dist
        sl_price = round(sl_price, digits)

        # 3. Calculate Final TP
        # Extract conviction from comment if possible, else default to 0.80
        conv_val = 0.80
        if "P0." in pos.comment:
            try:
                idx = pos.comment.find("P0.")
                conv_str = pos.comment[idx+1:idx+5]
                conv_val = float(conv_str)
            except:
                pass
                
        p_entry = conv_val if direction == "BUY" else (1.0 - conv_val)
        if p_entry < 0.5:
            p_entry = abs(conv_val - 0.5) + 0.5
        p_entry = max(p_entry, 0.60)
        
        normalized_p = (p_entry - 0.60) / 0.40
        tp_multiplier = 2.0 + 2.0 * math.log10(1 + 9 * normalized_p)
        tp_dist = d1_atr * tp_multiplier
        
        SYMMETRIC_TP_RATIO = 1.5
        symmetric_tp_floor = final_sl_dist * SYMMETRIC_TP_RATIO
        if tp_dist < symmetric_tp_floor:
            tp_dist = symmetric_tp_floor

        tp_price = entry_price + tp_dist if direction == "BUY" else entry_price - tp_dist
        tp_price = round(tp_price, digits)

        # Check if already correct to avoid spam
        if abs(pos.sl - sl_price) < info.point and abs(pos.tp - tp_price) < info.point:
            logger.info(f"[{symbol}] Ticket #{ticket} already correctly anchored. SL={sl_price:.5f}, TP={tp_price:.5f}")
            continue

        # 4. Modify Position
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": symbol,
            "sl": sl_price,
            "tp": tp_price
        }

        logger.info(f"[{symbol}] Modifying Ticket #{ticket}: OldSL={pos.sl:.5f}->NewSL={sl_price:.5f} | OldTP={pos.tp:.5f}->NewTP={tp_price:.5f}")
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"[{symbol}] Modification failed for Ticket #{ticket}: {result.comment}")
        else:
            logger.info(f"[{symbol}] Successfully re-anchored Ticket #{ticket}")

    mt5.shutdown()

if __name__ == '__main__':
    reanchor_positions()