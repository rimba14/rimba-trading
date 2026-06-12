import os
import sys
import time
import json
import MetaTrader5 as mt5

# Add paths to make sure we can import other gitagent modules if needed
sys.path.append(r"C:\Users\ADMIN\.antigravity\rimba-trading")
sys.path.append(r"C:\Sentinel_Project")

import sentinel_config as cfg
import gitagent_utils as utils

# State bridge directories
STATE_DIR = r"C:\Sentinel_Project\data"
if not os.path.exists(STATE_DIR):
    STATE_DIR = r"C:\Users\ADMIN\.antigravity\rimba-trading\data"
CONSENSUS_FILE = os.path.join(STATE_DIR, "consensus_state.json")

def execute_order(symbol, direction, volume=0.01):
    """Sends a direct execution request to the MT5 Terminal."""
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"[EXECUTE_ERR] Failed to get tick for {symbol}")
        return False
        
    price = tick.ask if direction == "BUY" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    
    # Calculate hard stops using simple ATR proxy or 3.5x ATR default
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 20)
    if rates is not None and len(rates) > 0:
        highs = [r['high'] for r in rates]
        lows = [r['low'] for r in rates]
        closes = [r['close'] for r in rates]
        tr_list = []
        for i in range(1, len(rates)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            tr_list.append(tr)
        atr = sum(tr_list) / len(tr_list) if tr_list else 0.0010
    else:
        atr = 0.0010
        
    atr = max(atr, 0.0020 * price) # 0.20% floor
    
    digits = mt5.symbol_info(symbol).digits if mt5.symbol_info(symbol) else 5
    sl = price - (3.5 * atr) if direction == "BUY" else price + (3.5 * atr)
    tp = price + (5.25 * atr) if direction == "BUY" else price - (5.25 * atr)
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": float(price),
        "sl": float(round(sl, digits)),
        "tp": float(round(tp, digits)),
        "deviation": 20,
        "magic": cfg.MAGIC_NUMBER,
        "comment": f"v37.0 {direction}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    # Severed autonomous trigger for HITL mandate
    print(f"[HITL_ENFORCED] Autonomous order execution BLOCKED for {symbol} {direction}. Order routing is deprecated.")
    return False
    # res = mt5.order_send(request)
    # if res and res.retcode == mt5.TRADE_RETCODE_DONE:
    #     print(f"[EXECUTE_SUCCESS] Executed {direction} on {symbol} (Ticket: {res.order})")
    #     return True
    # else:
    #     print(f"[EXECUTE_FAIL] Failed to execute {direction} on {symbol}: {res.comment if res else 'No Response'}")
    #     return False

def main():
    print("[FAST_LOOP] Starting 1-second Vantage Execution Order Router...")
    if not mt5.initialize():
        print("[FAST_LOOP_ERR] MT5 initialization failed.")
        sys.exit(1)
        
    last_processed_ts = 0
    
    while True:
        try:
            if not os.path.exists(CONSENSUS_FILE):
                time.sleep(1)
                continue
                
            # Read consensus state from disk
            with open(CONSENSUS_FILE, "r") as f:
                consensus = json.load(f)
                
            timestamp = consensus.get("timestamp", 0)
            
            # Only process fresh signals
            if timestamp > last_processed_ts:
                # Enforce freshness threshold (must be less than 5 seconds old)
                age = time.time() - timestamp
                if age < 5.0:
                    signals = consensus.get("signals", {})
                    for symbol, action in signals.items():
                        if action in ["BUY", "SELL"]:
                            # 1. Duplicate Guard check
                            open_positions = mt5.positions_get(symbol=symbol)
                            if open_positions:
                                print(f"[DUPLICATE_GUARD] Blocked duplicate signal {action} for {symbol}.")
                                continue
                                
                            # 2. Execute order
                            execute_order(symbol, action)
                            
                last_processed_ts = timestamp
                
        except Exception as e:
            print(f"[FAST_LOOP_ERR] Error in Vantage execution router: {e}")
            
        time.sleep(1)
        
    mt5.shutdown()

if __name__ == "__main__":
    main()
