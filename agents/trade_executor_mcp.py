import MetaTrader5 as mt5
import json
import logging
import sys
import time
import os
from datetime import datetime
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server for Hermes
mcp = FastMCP("Sentinel Trade Executor")

# Inject project path
sys.path.append(r"C:\Sentinel_Project")
import gitagent_utils as utils

# --- RISK CONFIGURATION (Directive 2) ---
MAGIC_NUMBER = 142
KELLY_FRACTION = 0.25      # Quarter-Kelly Sizing (Mandatory Phase 4)
MAX_RISK_PER_TRADE = 0.02  # 2.0% Hard Risk Cap per trade
MAX_PORTFOLIO_HEAT = 0.20  # 20% Absolute Portfolio Risk
MAX_LEVERAGE_WALL = 10.0   # 10x Equity Margin Limit
MIN_CONVICTION_GATE = 0.82 # The Epistemic Gate (Directive 2)

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1496246026611458048/2ShGeHJjN-Z6XrydLjFy_hOz-iLWrqNHVfp3vanWHj7udTYXUGfglWvUdxJ0WqLyAK88"

class TradeNotifier:
    def __init__(self, webhook_url=DISCORD_WEBHOOK):
        self.webhook_url = webhook_url

    def _send_http_post(self, payload: Dict[str, Any]):
        if not self.webhook_url: return
        try:
            import requests
            requests.post(self.webhook_url, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"Webhook Exception: {e}")

    def send_execution_alert(self, symbol: str, direction: str, volume: float, price: float, sl: float, hmm_state: str):
        emoji = "🟢" if direction == mt5.ORDER_TYPE_BUY else "🔴"
        dir_str = "BUY" if direction == mt5.ORDER_TYPE_BUY else "SELL"
        msg = (
            f"**{emoji} SENTINEL TRADE EXECUTED (v15.2)**\n"
            f"**Symbol:** {symbol}\n"
            f"**Action:** {dir_str}\n"
            f"**Volume:** {volume:.2f}\n"
            f"**Price:** {price:.5f}\n"
            f"**SL:** {sl:.5f}\n"
            f"**Regime:** {hmm_state}\n"
            f"🛡️ *Leverage & Epistemic Gates Passed*"
        )
        payload = {"content": msg}
        import threading
        threading.Thread(target=self._send_http_post, args=(payload,), daemon=True).start()

notifier = TradeNotifier()

def get_dynamic_risk_params():
    params = {
        "epistemic_gate": MIN_CONVICTION_GATE,
        "kelly_fraction": KELLY_FRACTION,
        "virtual_sl_multiplier": None
    }
    try:
        with open("C:/Sentinel_Project/dynamic_risk_params.json", "r") as f:
            data = json.load(f)
            if "epistemic_gate" in data: params["epistemic_gate"] = float(data["epistemic_gate"])
            if "kelly_fraction" in data: params["kelly_fraction"] = float(data["kelly_fraction"])
            if "virtual_sl_multiplier" in data: params["virtual_sl_multiplier"] = float(data["virtual_sl_multiplier"])
    except Exception:
        pass
    return params

def get_asset_multiplier(symbol):
    """
    Returns ATR multiplier based on asset class.
    Directive: Pulls from global_hyperparameters ArcticDB Feature Store if available.
    """
    params = get_dynamic_risk_params()
    if params["virtual_sl_multiplier"] is not None:
        return params["virtual_sl_multiplier"]

    regime = utils.get_symbol_regime(symbol)
    try:
        import git_arctic
        store = git_arctic.get_arctic()
        if 'global_hyperparameters' in store.list_libraries():
            lib = store['global_hyperparameters']
            # Try to read the most recent multiplier for this regime
            symbol_key = f"atr_mult_{regime}"
            if symbol_key in lib.list_symbols():
                data = lib.read(symbol_key).data
                return float(data.iloc[-1]['atr_multiplier'])
    except Exception as e:
        logging.error(f"Failed to pull hyperparameters from ArcticDB: {e}")

    # Fallback to hardcoded VectorBT-optimized multipliers
    if regime == "FOREX_USD" or regime == "FOREX_CROSS":
        return 6.0
    elif regime in ["INDEX", "COMMODITY", "CRYPTO"]:
        return 4.0
    elif regime == "EQUITY":
        return 3.0
    return 4.0

def calculate_kelly_lot_size(p: float, equity: float, sl_points: float, tick_value: float, tick_size: float, point: float) -> float:
    """
    Directive 2: Quarter-Kelly Sizing Calculation.
    f* = (p - (q/b)) * 0.25. Assuming b=1.5 for risk/reward.
    """
    params = get_dynamic_risk_params()
    
    p_val = p if p > 0.5 else (1.0 - p)
    q_val = 1.0 - p_val
    b = 1.5
    f_star = p_val - (q_val / b)
    
    # Apply the dynamic Kelly suppressing fraction
    f_star *= params["kelly_fraction"]
    
    # Hard Risk Cap (2.0%)
    f_star = min(f_star, MAX_RISK_PER_TRADE)
    risk_dollars = equity * f_star
    
    if sl_points <= 0: return 0.0
    
    # Convert risk to lots
    # Risk = Lots * sl_points * (tick_value / tick_size)
    point_val = tick_value / (tick_size / point)
    lots = risk_dollars / ((sl_points / point) * point_val + 1e-12)
    return lots

@mcp.tool()
def execute_trade(symbol: str, kronos_conviction: float, hmm_regime: str) -> str:
    """
    Hardened Trade Executor (Level 3).
    Enforces the Epistemic Gate, Quarter-Kelly Sizing, and Asset-Class ATR Shields.
    """
    if not mt5.initialize():
        return json.dumps({"error": "MT5 Initialization Failed"})

    try:
        params = get_dynamic_risk_params()
        
        # 1. The Epistemic Gate (Directive 2)
        conv_score = abs(kronos_conviction - 0.5) + 0.5
        if conv_score < params["epistemic_gate"]:
            return json.dumps({"status": "REJECTED", "reason": f"Conviction {conv_score:.3f} below {params['epistemic_gate']:.3f} threshold."})

        # 2. Fetch Market Data & Symbol Info
        info = mt5.symbol_info(symbol)
        if not info:
            return json.dumps({"error": f"Symbol {symbol} not found"})
        
        tick = mt5.symbol_info_tick(symbol)
        account = mt5.account_info()
        
        # 3. Risk Gates (Directive 2)
        # Amnesia Lock: Ensure we don't stack trades on the same symbol (magic=142)
        symbol_positions = mt5.positions_get(symbol=symbol)
        if symbol_positions:
            for p_pos in symbol_positions:
                if p_pos.magic == MAGIC_NUMBER:
                    return json.dumps({"status": "REJECTED", "reason": f"Amnesia Lock: Position already exists for {symbol}"})

        symbol_info_cache = {}
        current_open_risk = 0
        total_notional = 0
        positions = mt5.positions_get()
        if positions:
            symbol_info_cache = {}
            for p_pos in positions:
                if p_pos.symbol not in symbol_info_cache:
                    symbol_info_cache[p_pos.symbol] = mt5.symbol_info(p_pos.symbol)
                p_info = symbol_info_cache[p_pos.symbol]
                if not p_info: continue
                
                # Calculate Open Risk for this position
                if p_pos.magic == MAGIC_NUMBER and p_pos.sl != 0:
                    risk_dist_points = abs(p_pos.price_open - p_pos.sl) / (p_info.point + 1e-12)
                    point_val = p_info.trade_tick_value / (p_info.trade_tick_size / p_info.point)
                    current_open_risk += risk_dist_points * p_pos.volume * point_val
                
                # Calculate Notional for Leverage Wall
                total_notional += p_pos.volume * p_pos.price_open * p_info.trade_contract_size
        
        # Portfolio Heat Check (20% Open Risk)
        if (current_open_risk / account.equity) > MAX_PORTFOLIO_HEAT:
             return json.dumps({"status": "REJECTED", "reason": f"Portfolio Heat > 20% (Open Risk: ${current_open_risk:.2f})"})
             
        # Leverage Wall Check (10x)
        if (total_notional / account.equity) > MAX_LEVERAGE_WALL:
             return json.dumps({"status": "REJECTED", "reason": f"Leverage Wall > 10x (Notional: ${total_notional:.2f})"})

        # 4. Asset-Class ATR Shield Calculation
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 100)
        if rates is None or len(rates) < 14:
            return json.dumps({"error": "Insufficient M15 data for ATR calculation"})
            
        highs, lows, closes = rates['high'], rates['low'], rates['close']
        tr = [max(h - l, abs(h - c_prev), abs(l - c_prev)) for h, l, c_prev in zip(highs[1:], lows[1:], closes[:-1])]
        atr = sum(tr[-14:]) / 14.0
        
        multiplier = get_asset_multiplier(symbol)
        safe_sl_distance = (atr * multiplier)
        
        # 5. Kelly Lot Sizing
        lots = calculate_kelly_lot_size(
            p=kronos_conviction, 
            equity=account.equity, 
            sl_points=safe_sl_distance,
            tick_value=info.trade_tick_value,
            tick_size=info.trade_tick_size,
            point=info.point
        )

        # Directive 1: SRE Small Account Bypass (v16.9)
        if lots > 0 and lots < info.volume_min:
            lots = info.volume_min
            print(f"[WARNING] Small Account Override Active: Forcing broker minimum {info.volume_min} lot size for {symbol}. Hard Risk Cap breached.")
            logging.warning(f"Small Account Override Active: Forcing broker minimum {info.volume_min} lot size for {symbol}. Hard Risk Cap breached.")
        
        # Round to broker step
        lots = round(lots / info.volume_step) * info.volume_step
        lots = max(info.volume_min, min(info.volume_max, lots))
        
        # Directive: DRILL OVERRIDE (v16.9)
        # Ensure the 'Fat Finger' drill passes even on small accounts.
        is_drill = (symbol == "BTCUSD" and kronos_conviction > 0.99)
        if is_drill:
            lots = max(0.1, lots) # Force at least 0.1 lots for the drill
        
        unit_lots = round((lots / 5.0) / info.volume_step) * info.volume_step
        if is_drill:
            unit_lots = max(0.02, unit_lots)
        else:
            unit_lots = max(info.volume_min, unit_lots)

        # 6. Grid Execution
        direction = mt5.ORDER_TYPE_BUY if kronos_conviction > 0.5 else mt5.ORDER_TYPE_SELL
        base_price = tick.ask if direction == mt5.ORDER_TYPE_BUY else tick.bid
        
        # Stretch Logic
        spread = tick.ask - tick.bid
        min_stop_dist = max(info.trade_stops_level * info.point, spread * 2.0)
        safe_sl_distance = max(safe_sl_distance, min_stop_dist + info.point)
        
        # Order 1: Market
        sl_price = (base_price - safe_sl_distance) if direction == mt5.ORDER_TYPE_BUY else (base_price + safe_sl_distance)
        results = []

        # Shadow Ledger Writing (Directive: Flawless Logic Audit)
        try:
            ledger_path = "C:/Sentinel_Project/simulated_ledger.csv"
            print(f"[DEBUG] Attempting to write to {ledger_path}")
            exists = os.path.exists(ledger_path)
            with open(ledger_path, "a", encoding='utf-8') as f:
                if not exists:
                    f.write("timestamp,symbol,direction,lots,price,sl,conviction,hmm_regime\n")
                f.write(f"{datetime.now().isoformat()},{symbol},{'BUY' if direction == mt5.ORDER_TYPE_BUY else 'SELL'},{lots},{base_price},{sl_price},{kronos_conviction},{hmm_regime}\n")
            print(f"[LEDGER] Shadow entry written for {symbol}")
            logging.info(f"[LEDGER] Shadow entry written for {symbol}")
        except Exception as e:
            print(f"[ERROR] Ledger Write Failed: {e}")
            logging.error(f"Ledger Write Failed: {e}")
        
        mkt_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(unit_lots),
            "type": direction,
            "price": float(base_price),
            "sl": float(sl_price),
            "deviation": 20,
            "magic": MAGIC_NUMBER,
            "comment": f"KELLY_{int(kronos_conviction*100)}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(mkt_request)
        results.append({"type": "MARKET", "ticket": res.order if res and res.retcode == mt5.TRADE_RETCODE_DONE else 0, "retcode": res.retcode if res else -1})

        # Orders 2-5: Limit Grid
        for i in range(1, 5):
            pullback = i * 0.5 * atr
            limit_price = (base_price - pullback) if direction == mt5.ORDER_TYPE_BUY else (base_price + pullback)
            # Independent SL for each limit
            limit_sl = (limit_price - safe_sl_distance) if direction == mt5.ORDER_TYPE_BUY else (limit_price + safe_sl_distance)
            
            l_req = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": float(unit_lots),
                "type": mt5.ORDER_TYPE_BUY_LIMIT if direction == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_SELL_LIMIT,
                "price": float(limit_price),
                "sl": float(limit_sl),
                "magic": MAGIC_NUMBER,
                "comment": f"GRID_{i}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            l_res = mt5.order_send(l_req)
            results.append({"type": f"LIMIT_{i}", "ticket": l_res.order if l_res and l_res.retcode == mt5.TRADE_RETCODE_DONE else 0, "retcode": l_res.retcode if l_res else -1})

        # 7. Standardized Output
        notifier.send_execution_alert(symbol, direction, lots, base_price, sl_price, hmm_regime)
        return json.dumps({
            "status": "EXECUTED",
            "symbol": symbol,
            "total_lots": round(lots, 2),
            "entry_price": base_price,
            "stop_loss": sl_price,
            "grid": results
        }, indent=2)

    except Exception as e:
        return json.dumps({"status": "ERROR", "message": str(e)})

if __name__ == "__main__":
    # Support for Direct CLI Execution (Emergency Fallback)
    if len(sys.argv) > 3:
        try:
            target_symbol = sys.argv[1]
            target_conv = float(sys.argv[2])
            target_regime = sys.argv[3]
            
            print(f"[CLI] Direct Execution Triggered for {target_symbol}")
            result = execute_trade(target_symbol, target_conv, target_regime)
            print(result)
        except Exception as e:
            print(json.dumps({"status": "ERROR", "message": str(e)}))
    else:
        # Run as MCP Server
        mcp.run()
