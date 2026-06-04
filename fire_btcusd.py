import sys
import logging
import MetaTrader5 as mt5
import math

sys.path.append(r"C:\Sentinel_Project")
from fastapi_sniper import (
    calculate_kelly_lot,
    calculate_atr_and_swing, 
    atomic_sl_tp_modification,
    get_broker_adapter,
    MAGIC_NUMBER
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FireBTC")

def main():
    path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    if not mt5.initialize(path=path):
        logger.error(f"MT5 initialization failed: {mt5.last_error()}")
        sys.exit(1)

    symbol = "BTCUSD"
    conviction = 0.8416
    direction = "BUY"
    
    logger.info("Initializing manual override trade execution for BTCUSD (Wide ATR Stop Loss)...")
    
    # 1. Calculate Lot Size
    lot_size = calculate_kelly_lot(symbol, conviction)
    logger.info(f"Calculated Kelly Lot size: {lot_size}")
    
    info = mt5.symbol_info(symbol)
    if not info:
        logger.error(f"Symbol info for {symbol} not found.")
        mt5.shutdown()
        sys.exit(1)
        
    if lot_size <= 0.0:
        logger.warning(f"Calculated lot size is {lot_size}. Falling back to broker minimum {info.volume_min} for manual override.")
        lot_size = info.volume_min
        
    # Cap to max volume allowed by broker/account
    lot_size = min(max(lot_size, info.volume_min), info.volume_max)
    logger.info(f"Executing manual override order of {lot_size} lots on {symbol}...")

    # 2. Execute Order via Adapter
    adapter = get_broker_adapter(symbol)
    ticket_id_str = adapter.execute_market_order(
        symbol=symbol,
        lots=lot_size,
        direction=direction,
        comment="MANUAL_OVERRIDE_BTCUSD_WIDE"
    )
    
    if ticket_id_str == "ERROR_TICKET_FAILED" or not ticket_id_str.isdigit():
        logger.error("Failed to execute order via MT5Adapter.")
        mt5.shutdown()
        sys.exit(1)
        
    ticket_id = int(ticket_id_str)
    logger.info(f"Market order executed successfully. Ticket: {ticket_id}")

    # 3. Calculate SL/TP
    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if direction == "BUY" else tick.bid
    digits = info.digits
    
    # ATR calculation
    current_atr, _ = calculate_atr_and_swing(symbol, direction, lookback=20)
    
    # Force 3.0x ATR Stop Loss distance for noise protection
    final_sl_dist = 3.0 * current_atr
    broker_minimum_sl = info.trade_stops_level * info.point if info else 0.0001
    final_sl_dist = max(final_sl_dist, broker_minimum_sl)
    
    logger.info(f"CADES SL: ATR={current_atr:.5f} | Forcing 3.0x ATR SL Distance={final_sl_dist:.5f}")
    
    sl_price = price - final_sl_dist if direction == "BUY" else price + final_sl_dist
    sl_price = round(sl_price, digits)

    # TP Calculation (scaled by conviction)
    p_entry = conviction
    normalized_p = (p_entry - 0.60) / 0.40
    tp_multiplier = 2.0 + 2.0 * math.log10(1 + 9 * normalized_p)
    tp_dist = current_atr * tp_multiplier
    
    tp_price = price + tp_dist if direction == "BUY" else price - tp_dist
    tp_price = round(tp_price, digits)

    logger.info(f"Calculated Stops for modification: SL={sl_price:.2f}, TP={tp_price:.2f}")

    # 4. Attach Stops via ECN-Safe post-execution modification
    positions = mt5.positions_get(ticket=ticket_id)
    if not positions:
        logger.error(f"Could not retrieve filled position for Ticket {ticket_id} to attach stops.")
        mt5.shutdown()
        sys.exit(1)
        
    pos = positions[0]
    success = atomic_sl_tp_modification(pos, sl_price, tp_price)
    
    if success:
        logger.info(f"[SUCCESS] Position stops attached successfully for ticket {ticket_id}.")
        print(f"\n[MANUAL OVERRIDE SUCCESS] BTCUSD BUY {lot_size} lots executed. Ticket: {ticket_id} | SL: {sl_price} | TP: {tp_price}")
    else:
        logger.error(f"[PARTIAL SUCCESS] Position executed but stops attachment failed. Ticket: {ticket_id}")
        print(f"\n[PARTIAL EXECUTION SUCCESS] BTCUSD BUY {lot_size} lots executed. Ticket: {ticket_id} | Stops modification failed.")

    mt5.shutdown()

if __name__ == "__main__":
    main()
