import MetaTrader5 as mt5
import os
import json
import time
import logging
import sys
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# Inject project path
sys.path.append(r"C:\Sentinel_Project")
import git_arctic
from arcticdb import Arctic
import gitagent_utils as utils
import numpy as np
from scipy.stats import norm, skew, kurtosis

# Configure Logging
log_file = r"C:\sentinel_logs\profit_manager_v15_6.log"
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [PROFIT_MANAGER] %(message)s',
    force=True,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file)
    ]
)

MAGIC_NUMBER = 142
DIAGNOSTICS_DIR = "pending_diagnostics"
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

def calculate_psr(returns, benchmark_sr=0.0):
    """
    Directive 1: Probabilistic Sharpe Ratio (PSR).
    Penalizes negative skewness and excess kurtosis.
    """
    n = len(returns)
    if n < 15: return 0.50 # Not enough data for meaningful PSR
    
    # Calculate Annualized Sharpe (assuming returns are per-trade)
    mu = np.mean(returns)
    sigma = np.std(returns) + 1e-9
    sr = mu / sigma
    
    sk = skew(returns)
    ku = kurtosis(returns, fisher=True) # Excess kurtosis
    
    # Standard deviation of the SR estimate
    sigma_sr = np.sqrt((1 - sk * sr + (ku / 4) * sr**2) / (n - 1))
    
    # Probabilistic Sharpe Ratio
    psr = norm.cdf((sr - benchmark_sr) / sigma_sr)
    return psr

def run_psr_audit():
    """
    Directive 2: The SRE Circuit Breaker.
    Triggers PSR_DEGRADATION if edge falls below 80%.
    """
    try:
        from_date = datetime.now() - timedelta(days=30)
        deals = mt5.history_deals_get(from_date, datetime.now())
        if not deals: return
        
        # Filter for our magic number and closed trades (entry=1)
        profits = [d.profit for d in deals if d.magic == MAGIC_NUMBER and d.entry == 1]
        
        if len(profits) >= 50:
            psr_val = calculate_psr(profits)
            logging.info(f"[PSR_AUDIT] Samples: {len(profits)} | PSR: {psr_val:.2%}")
            
            if psr_val < 0.80:
                logging.warning(f"[SRE_TRIPWIRE] PSR DEGRADATION DETECTED: {psr_val:.2%}")
                
                # Throw Diagnostic to trigger Hermes SRE Mode
                diag = {
                    "error_type": "PSR_DEGRADATION",
                    "psr_value": psr_val,
                    "trade_count": len(profits),
                    "action_required": "HALT_NEW_SUBORDERS",
                    "timestamp": time.time()
                }
                diag_file = os.path.join(DIAGNOSTICS_DIR, f"psr_fail_{int(time.time())}.json")
                with open(diag_file, 'w') as f: json.dump(diag, f, indent=4)
                
    except Exception as e:
        logging.error(f"PSR Audit Error: {e}")

def close_position(pos, reason, context=None):
    """Closes a position and logs the reason. Embeds failures to FAISS graveyard."""
    tick = mt5.symbol_info_tick(pos.symbol)
    if not tick: return False
    
    type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
    
    # Directive 2 (The FAISS Post-Mortem Graveyard)
    if "STOP" in reason.upper() or "BREACH" in reason.upper():
        try:
            import gitagent_memory as hermes_mem
            import gitagent_sigproc as sigproc
            mem = hermes_mem.EpisodicMemory(dim=93)
            
            # Construct 93-dim vector
            vec = sigproc.get_feature_vector_native(pos.symbol)
            if context:
                # Slot 60: HMM State (BULL=0, BEAR=1, RANGE=2, VOLATILE=3)
                hmm_map = {"BULL": 0, "BEAR": 1, "RANGE": 2, "VOLATILE": 3}
                vec[60] = hmm_map.get(context.get('hmm_state'), 2)
                vec[61] = float(context.get('kronos_conviction', 0.5))
                vec[62] = float(context.get('vol_pct', 0.0))
                
                regime = context.get('regime', 'UNKNOWN')
                regime_map = {"FOREX_USD": 0, "FOREX_CROSS": 1, "INDEX": 2, "COMMODITY": 3, "CRYPTO": 4, "EQUITY": 5}
                vec[63] = regime_map.get(regime, 6)
            
            mem.store(vec, action="FAILURE_STAY_OUT", pnl=float(pos.profit), 
                      reasoning=f"Post-Mortem: {reason} on {pos.symbol}", 
                      lesson="post_mortem_failure")
            logging.info(f"[GRAVEYARD] Embedded failed trade context for {pos.symbol} into FAISS.")
        except Exception as e:
            logging.error(f"Graveyard Embedding failed: {e}")
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": type,
        "position": pos.ticket,
        "price": price,
        "deviation": 9999,
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

def heal_stop_loss(item, expected_dist, is_pending=False):
    """
    Autonomous Trade Healing: Stretches the SL to the constitutionally mandated 
    ATR distance instead of liquidating.
    """
    symbol = item.symbol
    direction = item.type # For positions and orders, type mapping is consistent
    
    # 1. Calculate the New Compliant SL
    # We use price_open for positions and price_open (entry) for pending orders
    entry_price = item.price_open
    
    # Check if BUY or SELL
    is_buy = direction in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP]
    
    if is_buy:
        new_sl = entry_price - expected_dist
    else:
        new_sl = entry_price + expected_dist

    # 2. Execute Modification
    if is_pending:
        request = {
            "action": mt5.TRADE_ACTION_MODIFY,
            "order": item.ticket,
            "sl": new_sl,
            "tp": item.tp,
            "price": item.price_open
        }
    else:
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": item.ticket,
            "sl": new_sl,
            "tp": item.tp
        }
    
    res = mt5.order_send(request)
    if res.retcode == mt5.TRADE_RETCODE_DONE:
        logging.info(f"[{symbol}] HEALED ticket {item.ticket} ({'PENDING' if is_pending else 'LIVE'}). New SL: {new_sl:.5f}")
        return True, new_sl
    else:
        logging.error(f"[{symbol}] Healing FAILED for ticket {item.ticket}. Retcode: {res.retcode}")
        return False, 0

def perform_wakeup_audit(lib):
    """
    Directive 3 (v15.5): Wake-Up Protocol.
    Ensures all resting orders have correct Catastrophe Stops and flattens breached positions.
    """
    logging.info("--- [WAKE-UP] Initializing v15.5 Hybrid Audit ---")
    if not mt5.initialize(): return
    
    positions = mt5.positions_get() or []
    orders = mt5.orders_get() or []
    
    for item in list(positions) + list(orders):
        if item.magic != MAGIC_NUMBER: continue
        
        symbol = item.symbol
        is_pending = hasattr(item, 'state') # Orders have state, positions don't
        
        try:
            k_item = lib.read(f"{symbol}_kronos")
            if not k_item: continue
            base_atr = float(k_item.data.iloc[-1].get('base_atr', 0.0))
            if base_atr <= 0: continue
            
            multiplier = get_asset_multiplier(symbol)
            virtual_dist = base_atr * multiplier
            catastrophe_dist = virtual_dist * 2.0
            
            # 1. Wake-Up Logic for Pending Limits
            if is_pending and item.type in [mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT]:
                current_sl_dist = abs(item.price_open - item.sl) if item.sl != 0 else 0
                # If SL is too tight (< 1.9x to allow buffer) or missing
                if current_sl_dist < catastrophe_dist * 0.95:
                    logging.info(f"[{symbol}] [WAKE-UP] Adjusting Pending SL for ticket {item.ticket} to Catastrophe boundary.")
                    heal_stop_loss(item, catastrophe_dist, is_pending=True)

            # 2. Wake-Up Logic for Live Positions (Flatten if breached)
            elif not is_pending:
                tick = mt5.symbol_info_tick(symbol)
                if not tick: continue
                
                price = tick.bid if item.type == mt5.ORDER_TYPE_BUY else tick.ask
                
                # Directive (v16.8): Physical Integrity Check
                # Since virtual stops are prohibited, we only flatten if the position 
                # exists without a hard SL or if the SL is drastically misaligned.
                if item.sl == 0:
                    logging.warning(f"[{symbol}] [WAKE-UP] Position {item.ticket} missing Physical SL. Healing...")
                    heal_stop_loss(item, base_atr * get_asset_multiplier(symbol), is_pending=False)

        except Exception as e:
            logging.error(f"Wake-up error for {symbol}: {e}")

def audit_and_manage():
    """Main audit and management loop (v15.5 Hybrid Build)."""
    if not mt5.initialize():
        return

    from arcticdb import Arctic
    store = Arctic('lmdb://./data/arctic_cache')
    lib = store['oracle_cache']

    # Directive 3: Run Wake-Up Protocol once on start
    perform_wakeup_audit(lib)
    
    last_psr_check = 0

    while True:
        try:
            # Run PSR Audit every 10 minutes (or every trade if needed)
            if time.time() - last_psr_check > 600:
                run_psr_audit()
                last_psr_check = time.time()
            positions = list(mt5.positions_get() or [])
            pending_orders = list(mt5.orders_get() or [])
            
            all_items = [(p, False) for p in positions] + [(o, True) for o in pending_orders]

            if not all_items:
                time.sleep(10)
                continue

            for item, is_pending in all_items:
                if item.magic != MAGIC_NUMBER:
                    continue

                symbol = item.symbol
                
                # 1. Fetch Cache Data with Staleness Gate
                try:
                    k_item = lib.read(f"{symbol}_kronos")
                    h_item = lib.read(f"{symbol}_hmm")
                    if not k_item or not h_item: continue
                    
                    k_data = k_item.data.iloc[-1]
                    h_data = h_item.data.iloc[-1]
                    
                    # Staleness Gate
                    cache_ts = float(h_data.get('timestamp', 0))
                    if time.time() - cache_ts > 300:
                        logging.warning(f"[{symbol}] [AWAITING_FRESH_CACHE] Data stale. HOLD.")
                        continue
                    
                    kronos_conviction = float(k_data.get('kronos_prob', 0.5))
                    hmm_state = h_data.get('state', 'RANGE')
                    base_atr = float(k_data.get('base_atr', 0.0))
                    
                    context = {
                        "hmm_state": hmm_state,
                        "kronos_conviction": kronos_conviction,
                        "vol_pct": float(k_data.get('vol_pct', 0.0)),
                        "regime": utils.get_symbol_regime(symbol)
                    }
                except:
                    continue

                # Directive (v16.8): Physical Seatbelt Logic
                # Purely 'Virtual' stops are prohibited for base risk management.
                multiplier = get_asset_multiplier(symbol)
                hard_sl_dist = base_atr * multiplier

                # 2. Regime Inversion & Logic Exits (Only for Live Positions)
                if not is_pending:
                    tick = mt5.symbol_info_tick(symbol)
                    if not tick: continue
                    
                    # A. Physical Stop Integrity Check
                    # (Broker-side SL is our primary defense)
                    pass

                    # B. Regime Inversion
                    if item.type == mt5.ORDER_TYPE_BUY and hmm_state == 'BEAR':
                        close_position(item, "REGIME_INVERSION_BEAR", context=context)
                        continue
                    if item.type == mt5.ORDER_TYPE_SELL and hmm_state == 'BULL':
                        close_position(item, "REGIME_INVERSION_BULL", context=context)
                        continue

                    # C. Alternative Data Oracle (Black Swan Shield)
                    sentiment = utils.fetch_unstructured_sentiment(symbol)
                    if item.type == mt5.ORDER_TYPE_BUY and sentiment < -0.60:
                        close_position(item, f"SENTIMENT_EXIT_BEAR_{sentiment:.2f}", context=context)
                        continue
                    if item.type == mt5.ORDER_TYPE_SELL and sentiment > 0.60:
                        close_position(item, f"SENTIMENT_EXIT_BULL_{sentiment:.2f}", context=context)
                        continue

                    # D. Conviction Decay
                    conv_score = abs(kronos_conviction - 0.5) + 0.5
                    if conv_score < 0.55:
                        close_position(item, f"CONVICTION_DECAY_{conv_score:.3f}", context=context)
                        continue

                # 3. Physical Stop Audit & Healing (Directive v16.8)
                # Hard SL must be active and correctly placed.
                current_sl_dist = abs(item.price_open - item.sl) if item.sl != 0 else 0
                
                if current_sl_dist == 0 or current_sl_dist > hard_sl_dist * 1.10:
                    logging.warning(f"[{symbol}] Physical SL missing or too wide. Healing...")
                    success, healed_sl = heal_stop_loss(item, hard_sl_dist, is_pending)
                    if success:
                        diag = {
                            "error_type": "PHYSICAL_SL_HEALING",
                            "symbol": symbol,
                            "ticket": item.ticket,
                            "healed_sl_distance": round(abs(item.price_open - healed_sl), 5),
                            "timestamp": time.time()
                        }
                        diag_file = os.path.join(DIAGNOSTICS_DIR, f"heal_{symbol}_{int(time.time())}.json")
                        with open(diag_file, 'w') as f: json.dump(diag, f, indent=4)
                    continue

                # 4. Physical Trailing Stop (Directive v16.8)
                # We physically drag the broker-side stop deep into profit.
                if not is_pending:
                    if item.type == mt5.ORDER_TYPE_BUY:
                        new_trail_sl = tick.bid - hard_sl_dist
                        if new_trail_sl > item.sl + (base_atr * 0.2):
                            logging.info(f"[{symbol}] Trailing Physical SL to {new_trail_sl:.5f}")
                            request = {"action": mt5.TRADE_ACTION_SLTP, "symbol": symbol, "position": item.ticket, "sl": new_trail_sl, "tp": item.tp}
                            mt5.order_send(request)
                    else:
                        new_trail_sl = tick.ask + hard_sl_dist
                        if item.sl == 0 or new_trail_sl < item.sl - (base_atr * 0.2):
                            logging.info(f"[{symbol}] Trailing Physical SL to {new_trail_sl:.5f}")
                            request = {"action": mt5.TRADE_ACTION_SLTP, "symbol": symbol, "position": item.ticket, "sl": new_trail_sl, "tp": item.tp}
                            mt5.order_send(request)

            time.sleep(5) 

        except Exception as e:
            logging.error(f"Profit Manager Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    logging.info("Starting Asynchronous Profit Manager v15.5 (Hybrid Seatbelt)...")
    audit_and_manage()
