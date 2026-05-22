import MetaTrader5 as mt5
import os
import json
import time
import logging
import sys
from datetime import datetime

# Inject project path
sys.path.append(r"C:\Sentinel_Project")
import git_arctic
import gitagent_utils as utils

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [PROFIT_MANAGER] %(message)s')

MAGIC_NUMBER = 142
DIAGNOSTICS_DIR = r"C:\Sentinel_Project\pending_diagnostics"
os.makedirs(DIAGNOSTICS_DIR, exist_ok=True)

def get_asset_multiplier(symbol):
    """Returns ATR multiplier based on asset class."""
    regime = utils.get_symbol_regime(symbol)
    if regime == "FOREX_USD" or regime == "FOREX_CROSS":
        return 6.0
    elif regime in ["INDEX", "COMMODITY", "CRYPTO"]:
        return 4.0
    elif regime == "EQUITY":
        return 3.0
    return 4.0

def close_position(pos, reason):
    """Closes a position and logs the reason."""
    tick = mt5.symbol_info_tick(pos.symbol)
    if not tick: return False
    
    # Identify closure type
    type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": type,
        "position": pos.ticket,
        "price": price,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": f"Exit_{reason}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    res = mt5.order_send(request)
    if res.retcode == mt5.TRADE_RETCODE_DONE:
        logging.info(f"[{pos.symbol}] Closed ticket {pos.ticket}. Reason: {reason}")
        return True
    else:
        logging.error(f"[{pos.symbol}] Failed to close ticket {pos.ticket}. Retcode: {res.retcode}")
        return False

def run_profit_manager():
    """Main audit and management loop."""
    if not mt5.initialize():
        logging.error('MT5 Init Failed')
        return

    logger = logging.getLogger("PROFIT_MANAGER")
    store = git_arctic.get_arctic()
    lib = store['oracle_cache']

    logger.info("--- Profit Manager v15.2 Online (Virtual Exits Active) ---")

    while True:
        try:
            positions = mt5.positions_get()
            if not positions:
                time.sleep(10)
                continue

            for pos in positions:
                if pos.magic != MAGIC_NUMBER:
                    continue

                symbol = pos.symbol
                
                # 1. Fetch Cache Data
                try:
                    k_item = lib.read(f"{symbol}_kronos")
                    h_item = lib.read(f"{symbol}_hmm")
                    if not k_item or not h_item: continue
                    
                    k_data = k_item.data.iloc[-1]
                    h_data = h_item.data.iloc[-1]
                    
                    kronos_conviction = float(k_data.get('kronos_prob', 0.5))
                    hmm_state = str(h_data.get('state', 'RANGE'))
                    base_atr = float(k_data.get('base_atr', 0.0))
                except Exception as e:
                    logger.warning(f"Cache read error for {symbol}: {e}")
                    continue

                # 2. Virtual Exit: Regime Inversion
                if pos.type == mt5.ORDER_TYPE_BUY and hmm_state == 'BEAR':
                    close_position(pos, "REGIME_INVERSION_BEAR")
                    continue
                if pos.type == mt5.ORDER_TYPE_SELL and hmm_state == 'BULL':
                    close_position(pos, "REGIME_INVERSION_BULL")
                    continue

                # 3. Virtual Exit: Conviction Decay (< 0.55)
                conv_score = abs(kronos_conviction - 0.5) + 0.5
                if conv_score < 0.55:
                    close_position(pos, f"CONVICTION_DECAY_{conv_score:.3f}")
                    continue

                # 4. Constitution Audit & SRE Tripwire (Healing Logic v15.2)
                multiplier = get_asset_multiplier(symbol)
                expected_sl_dist = base_atr * multiplier
                
                if pos.sl == 0:
                    logger.warning(f"[{symbol}] Ticket {pos.ticket} missing SL. Healing now...")
                    # Immediate healing for missing SL
                    direction = -1 if pos.type == mt5.ORDER_TYPE_BUY else 1
                    healed_sl = pos.price_open + (direction * expected_sl_dist)
                    
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": symbol,
                        "position": pos.ticket,
                        "sl": float(round(healed_sl, 5)),
                        "tp": pos.tp
                    })
                    continue

                actual_sl_dist = abs(pos.price_open - pos.sl)
                # Audit against the Asset-Class Multiplier (Constitutional Guardrail)
                if actual_sl_dist < expected_sl_dist * 0.95:
                    logger.error(f"[CONSTITUTION_BREACH] {symbol} Ticket {pos.ticket}: SL {actual_sl_dist:.5f} < Min {expected_sl_dist:.5f}")
                    
                    # HEALING: Modify SL instead of closing
                    direction = -1 if pos.type == mt5.ORDER_TYPE_BUY else 1
                    healed_sl = pos.price_open + (direction * expected_sl_dist)
                    
                    res = mt5.order_send({
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": symbol,
                        "position": pos.ticket,
                        "sl": float(round(healed_sl, 5)),
                        "tp": pos.tp
                    })
                    
                    if res.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info(f"[{symbol}] Ticket {pos.ticket} HEALED. SL stretched to {healed_sl:.5f}")
                    
                    # Drop diagnostic JSON for Hermes SRE Mode (New Schema)
                    diag = {
                        "error_type": "CONSTITUTION_BREACH",
                        "symbol": symbol,
                        "ticket": pos.ticket,
                        "faulty_sl_distance": round(actual_sl_dist, 5),
                        "healed_sl_distance": round(expected_sl_dist, 5),
                        "status": "HEAL_SUCCESSFUL",
                        "timestamp": time.time()
                    }
                    diag_file = os.path.join(DIAGNOSTICS_DIR, f"breach_{symbol}_{int(time.time())}.json")
                    with open(diag_file, 'w', encoding='utf-8') as f:
                        json.dump(diag, f, indent=4)
                    continue

                # 5. Dynamic Asset-Class ATR Trailing (Virtual Exit Extension)
                tick = mt5.symbol_info_tick(symbol)
                if not tick: continue
                
                if pos.type == mt5.ORDER_TYPE_BUY:
                    # Only trail if in profit by at least 1 ATR
                    if tick.bid > pos.price_open + base_atr:
                        new_sl = tick.bid - expected_sl_dist
                        if new_sl > pos.sl + (base_atr * 0.25): # Move in 0.25 ATR increments
                            mt5.order_send({
                                "action": mt5.TRADE_ACTION_SLTP,
                                "symbol": symbol,
                                "position": pos.ticket,
                                "sl": float(new_sl),
                                "tp": 0.0
                            })
                            logger.info(f"[{symbol}] Trailed SL to {new_sl:.5f}")
                else:
                    if tick.ask < pos.price_open - base_atr:
                        new_sl = tick.ask + expected_sl_dist
                        if new_sl < pos.sl - (base_atr * 0.25):
                            mt5.order_send({
                                "action": mt5.TRADE_ACTION_SLTP,
                                "symbol": symbol,
                                "position": pos.ticket,
                                "sl": float(new_sl),
                                "tp": 0.0
                            })
                            logger.info(f"[{symbol}] Trailed SL to {new_sl:.5f}")

            # --- GRID HEALING: Audit Pending Orders (v15.3 Directive) ---
            orders = mt5.orders_get()
            if orders:
                for o in orders:
                    # We only heal Sentinel trades (magic 142) that are Limit orders
                    if o.magic != 142 or o.type not in [mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT]:
                        continue
                    
                    symbol = o.symbol
                    base_atr = get_base_atr(symbol)
                    if base_atr == 0: continue
                    
                    multiplier = get_asset_multiplier(symbol)
                    expected_sl_dist = base_atr * multiplier
                    
                    # Current distance calculation
                    actual_sl_dist = abs(o.price_open - o.sl) if o.sl > 0 else 0
                    
                    # Directive 2 & 3: Trigger Healing if distance < expected
                    if actual_sl_dist < expected_sl_dist * 0.95 or o.sl == 0:
                        logger.warning(f"[GRID_HEAL] Order {o.ticket} ({symbol}): SL drift detected. Healing...")
                        
                        direction = -1 if o.type == mt5.ORDER_TYPE_BUY_LIMIT else 1
                        healed_sl = o.price_open + (direction * expected_sl_dist)
                        
                        request = {
                            "action": mt5.TRADE_ACTION_MODIFY,
                            "order": o.ticket,
                            "price": o.price_open,
                            "sl": float(round(healed_sl, 5)),
                            "tp": o.tp,
                            "type_time": o.type_time,
                            "type_filling": o.type_filling
                        }
                        
                        res = mt5.order_send(request)
                        
                        if res.retcode == mt5.TRADE_RETCODE_DONE:
                            logger.info(f"[GRID_HEAL] Order {o.ticket} ({symbol}) HEALED. SL stretched to {healed_sl:.5f}")
                            
                            # Directive 4: Update SRE Diagnostics for Hermes
                            diag = {
                                "error_type": "CONSTITUTION_BREACH",
                                "order_state": "PENDING", # Directive 4 Key
                                "symbol": symbol,
                                "ticket": o.ticket,
                                "faulty_sl_distance": round(actual_sl_dist, 5),
                                "healed_sl_distance": round(expected_sl_dist, 5),
                                "status": "HEAL_SUCCESSFUL",
                                "timestamp": time.time()
                            }
                            diag_file = os.path.join(DIAGNOSTICS_DIR, f"breach_pending_{symbol}_{int(time.time())}.json")
                            with open(diag_file, 'w', encoding='utf-8') as f:
                                json.dump(diag, f, indent=4)

            time.sleep(5) # Audit Cycle

        except Exception as e:
            logging.error(f"Profit Manager Exception: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_profit_manager()
