import MetaTrader5 as mt5
import gitagent_utils as utils
import gitagent_execute_sor as sor
import timesfm_bridge
import pandas as pd
import os
import time
from profit_manager_v28_34 import get_safe_atr
from gitagent_types import ProposedTradePayload
from verification_layer import underwriter
from broker_client import dispatch_permit


class ActionLayer:
    """
    ARCHITECTURE PHASE 1.4.2: THE RISK-GATED ACTION LAYER
    All trades must pass through here. Direct MT5 calls are forbidden in outer layers.
    """
    def __init__(self, min_margin_level=150.0, max_positions=30):
        self.min_margin_level = min_margin_level
        self.max_positions = max_positions
        self.ban_list = self._load_ban_list()

    def _load_ban_list(self):
        ban_list = []
        try:
            wiki_path = "C:\\Sentinel_Project\\TRADING_WIKI.md"
            if os.path.exists(wiki_path):
                with open(wiki_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "⚠️ TOXIC" in line:
                            sym_match = line.split("**")[1] if "**" in line else None
                            if sym_match: ban_list.append(sym_match)
        except Exception as e:
            print(f"[ACTION_ERR] Failed to load BAN_LIST: {e}")
        return ban_list

    def check_risk_gate(self, symbol):
        """Mandatory risk audit before any execution."""
        if symbol in self.ban_list:
            print(f"[RISK_GATE] {symbol} is BANNED (Toxic Asset)")
            return False, "BANNED"

        positions = mt5.positions_get()
        if positions is not None and len(positions) >= self.max_positions:
            print(f"[RISK_GATE] MAX_POSITIONS reached ({len(positions)})")
            return False, "MAX_POSITIONS"

        acc = mt5.account_info()
        if acc is None: return False, "NO_ACCOUNT_INFO"
        
        # MT5 sets margin_level to 0.0 when there are no open positions (margin == 0.0)
        if acc.margin > 0.0 and acc.margin_level < self.min_margin_level:
            print(f"[RISK_GATE] MARGIN_LEVEL too low: {acc.margin_level:.1f}%")
            return False, "MARGIN_GUARD"

        if not utils.is_market_open(symbol):
            print(f"[RISK_GATE] {symbol} Market is CLOSED")
            return False, "MARKET_CLOSED"

        return True, "NOMINAL"

    def execute_smart_trade(self, symbol, side, total_volume, current_price, atr, tps, equity, position_ticket=None):
        """
        Phase 3: Action Layer Execution & 5-Sub-Order Split
        Phase 5: Forensic Metadata Injection
        """
        allowed, reason = self.check_risk_gate(symbol)
        if not allowed: return None

        # FORCE INSTITUTIONAL ATR FLOOR ON ENTRY
        atr = get_safe_atr(symbol, atr, current_price)

        info = mt5.symbol_info(symbol)
        if not info: return None

        # Forensic Metadata: v142 {Direction} S:{TPS} A:{Entry_ATR}
        direction_flag = "BUY" if side == "BUY" else "SELL"
        metadata_comment = f"v142 {direction_flag} S:{int(tps*100)} A:{round(atr, 5)}"
        
        # Sub-order split (1 Market, 4 Limit at 0.5x ATR pullbacks)
        vol_step = info.volume_step
        vol_min = info.volume_min
        
        total_volume = max(total_volume, vol_min)
        total_volume = round(round(total_volume / vol_step) * vol_step, 2)
        
        chunk_vol = round(round((total_volume / 5.0) / vol_step) * vol_step, 2)
        if chunk_vol < vol_min:
            chunk_vol = total_volume
            num_chunks = 1
        else:
            num_chunks = 5
        
        orders = []
        for i in range(num_chunks):
            offset = i * 0.5 * atr
            target_price = current_price - offset if side == "BUY" else current_price + offset
            
            # P1 Hard Stop (TimesFM Oracle Override)
            p10, p90 = timesfm_bridge.get_cached_boundaries(symbol)
            if p10 is not None and p90 is not None:
                sl_price = p10 if side == "BUY" else p90
            else:
                # Fallback to ATR-based hard stop
                mult_hard = 10.0 if "XAUUSD" in symbol else 8.0
                sl_price = target_price - (mult_hard * atr) if side == "BUY" else target_price + (mult_hard * atr)
            
            # Formulate the Take Profit target
            tp_mult = 1.5
            if tps > 0:
                tp_mult = 2.0  # Basic expansion for demonstration
            tp_price = target_price + (tp_mult * atr) if side == "BUY" else target_price - (tp_mult * atr)

            # Build the Payload for Verification
            payload = ProposedTradePayload(
                symbol=symbol,
                side=side,
                volume=float(chunk_vol),
                current_price=target_price,
                requested_sl=sl_price,
                requested_tp=tp_price,
                macro_atr=atr,
                variance_p10=p10,
                variance_p90=p90
            )
            # Build the Draft Request for the Verification Engine
            draft_request = {
                "action": mt5.TRADE_ACTION_DEAL if i == 0 else mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "type": (mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL) if i == 0 else \
                        (mt5.ORDER_TYPE_BUY_LIMIT if side == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT),
                "price": round(float(target_price), info.digits),
                "comment": metadata_comment[:31],
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC if i == 0 else mt5.ORDER_FILLING_RETURN,
            }
            if position_ticket:
                draft_request["position"] = int(position_ticket)

            # --- PILLAR 1: INDEPENDENT UNDERWRITING ENGINE GATE ---
            permit = underwriter.underwrite_payload(payload, draft_request)
            
            if not permit.is_valid:
                print(f"[ACTION_LAYER] Trade for {symbol} REJECTED by Underwriting Engine pre-flight. Reason: {permit.rejection_reason}")
                for anomaly in payload.anomalies:
                    print(f" -> {anomaly}")
                break # Abort the entire sub-order loop if a hard veto occurs
            
            if payload.graceful_degradation_triggered:
                print(f"[ACTION_LAYER] {symbol} triggered Graceful Degradation. Parameters successfully padded.")

            # --- SYNCHRONOUS BROKER GATEWAY ---
            res = dispatch_permit(permit)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                orders.append(res.order)
            else:
                print(f"[SUB_ORDER_ERR] Part {i+1} failed: {res.comment if res else 'Unknown'}")
                break # If execution fails, abort further chunks

        
        return orders

    def audit_positions(self, sentinel, account_info):
        """Phase 4: The 5-Priority Exit & Stop Loss Audit"""
        positions = mt5.positions_get()
        if not positions: return

        equity = account_info.get('equity', 0)
        
        # P5: Portfolio Guard (Drawdown)
        breaker_tripped, action = sentinel.audit_circuit_breakers(equity, account_info)
        if breaker_tripped:
            if action == "LIQUIDATE_AND_HALT":
                print("[CIRCUIT_BREAKER] Phase 3 P5: LIQUIDATING ALL POSITIONS")
                self.liquidate_all()
                return
            elif action == "HALVE_POSITIONS":
                print("[CIRCUIT_BREAKER] Phase 3 P5: HALVING ALL POSITIONS")
                self.halve_all()

        for pos in positions:
            symbol = pos.symbol
            ticket = pos.ticket
            
            # Extract metadata from comment
            # Comment: v142 {Direction} S:{TPS} A:{Entry_ATR}
            try:
                parts = pos.comment.split(" ")
                entry_atr = float(parts[-1].split(":")[-1])
            except:
                entry_atr = 0 # Fallback
            
            # live ATR for trailing
            df = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 20)
            if df is None: continue
            df = pd.DataFrame(df)
            current_atr = df['high'].sub(df['low']).rolling(14).mean().iloc[-1]
            
            # HMM State (Mock/Fetch from global state)
            hmm_state = "RANGE" # Placeholder, usually provided by orchestrator

            # P1: Hard Stop (Entry ATR) - Already server-side but verified
            # P2: Live Trail (Current ATR) - Activate if > 1.5x entry_atr in profit
            profit_atr = abs(pos.price_current - pos.price_open) / (entry_atr + 1e-9)
            if profit_atr >= 1.5:
                levels = sentinel.get_stop_levels(symbol, pos.price_open, "BUY" if pos.type == 0 else "SELL", entry_atr, current_atr, hmm_state)
                # Apply trailing Sl logic...
                
            # P4: Time Exit (Coarsened to 15m intervals to prevent cycle spam)
            hours_open = (time.time() - pos.time) / 3600
            limit = 48 if "USD" in symbol else (24 if "XAU" in symbol else 8)
            if hours_open > limit:
                # Add 15m cooldown to prevent spamming failed closes
                now = time.time()
                last_exit = getattr(self, '_last_time_exit', {})
                if now - last_exit.get(ticket, 0) > 900: # 15 minutes
                    print(f"[TIME_EXIT] Phase 4 P4: Ticket {ticket} exceeded {limit}h. Attempting 50% Close")
                    if self.partial_close(ticket, 0.5):
                        last_exit[ticket] = now
                        self._last_time_exit = last_exit

    def liquidate_all(self):
        positions = mt5.positions_get()
        if not positions: return
        for p in positions:
            if not utils.is_market_open(p.symbol): continue
            sor.close_position(p.symbol, p.ticket)

    def halve_all(self):
        positions = mt5.positions_get()
        if not positions: return
        for p in positions:
            self.partial_close(p.ticket, 0.5)

    def partial_close(self, ticket, fraction):
        pos = mt5.positions_get(ticket=ticket)
        if not pos or len(pos) == 0: return False
        p = pos[0]
        if not utils.is_market_open(p.symbol): 
            print(f"[ACTION_LAYER] Skipping partial close on {p.symbol}: Market Closed")
            return False
        vol = round(p.volume * fraction, 2)
        if vol < 0.01: return False
        res = sor.close_partial(p.symbol, ticket, vol)
        return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE

# Singleton Instance
_ACTION_LAYER = ActionLayer()
def get_action_layer(): return _ACTION_LAYER

# Singleton Instance

_ACTION_LAYER = ActionLayer()

def get_action_layer():
    return _ACTION_LAYER
