import logging
import requests
import MetaTrader5 as mt5
from datetime import datetime, timezone

logger = logging.getLogger("CapitalWall")

class TradeRejected(Exception):
    """Custom exception raised when a trade is rejected by the CapitalWall constitution gates."""
    pass

class CapitalWall:
    def __init__(self, risk_agent_url="http://localhost:8001/check_trade"):
        self.risk_agent_url = risk_agent_url

    def check_risk_agent(self, signal, lot_size, price):
        """
        Wall 4: Risk Agent Circuit Breaker (Fail-Closed)
        Locate check_risk_agent(self, signal, lot_size, price)
        Change the base except Exception as e: block to fail closed (raise TradeRejected)
        """
        incoming_notional = lot_size * price
        payload = {
            "symbol": signal.symbol,
            "size_usd": incoming_notional,
            "leverage": 5.0,
            "xgb_p": getattr(signal, 'xgb_p', 0.5),
            "ddqn_p": getattr(signal, 'ddqn_p', 0.5)
        }
        try:
            resp = requests.post(self.risk_agent_url, json=payload, timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                if not data.get("allow"):
                    raise TradeRejected(f"[WALL4-FAIL] Risk Agent Veto: {data.get('reason')}")
                logger.info(f"[{signal.symbol}] Risk Agent authorized trade successfully.")
            elif resp.status_code == 403:
                err_reason = resp.json().get("detail", "Risk Agent Veto")
                raise TradeRejected(f"[WALL4-FAIL] Risk Agent 403 VETO: {err_reason}")
            else:
                raise TradeRejected(f"[WALL4-FAIL] Risk Agent returned unexpected status: {resp.status_code}")
        except TradeRejected:
            raise
        except Exception as e:
            # Tripped circuit breaker - Fail Closed!
            raise TradeRejected(f"[WALL4-FAIL] Risk Agent circuit breaker tripped: {e}. Trade aborted.")

    def check_event_horizon_blackout(self, signal):
        """
        Wall 5: Ex-Ante Macro Blackout
        Locate check_event_horizon_blackout(self, signal)
        Ensures no new entries are scaled down or allowed when a Tier-1 event is within 24 hours.
        """
        from agents.risk_agent import check_upcoming_tier1_events
        
        has_event, event_desc = check_upcoming_tier1_events(signal.symbol, threshold_hours=24.0)
        if has_event:
            raise TradeRejected(f"[WALL5-FAIL] Tier-1 event within 24h. Ex-Ante Blackout active. (Event: {event_desc})")

    def run(self, signal, lot_size, price):
        """
        Wall Run Pipeline: Evaluates all weekend, blackout, margin, and Risk Agent checks.
        Removes the scale multiplication and returns the unmodified lot_size if checks survive.
        """
        # 0. Daily Rollover Blackout (23:55 to 00:15 Broker Time)
        tick = mt5.symbol_info_tick(signal.symbol)
        if tick:
            dt = datetime.fromtimestamp(tick.time, timezone.utc)
            if (dt.hour == 23 and dt.minute >= 55) or (dt.hour == 0 and dt.minute <= 15):
                raise TradeRejected(f"[WALL5-FAIL] Rollover Liquidity Void: Trade rejected during daily rollover blackout (23:55 - 00:15 Broker Time).")

        # 1. Weekend Blackout Gate
        from fastapi_sniper import is_weekend_blackout
        if is_weekend_blackout(signal.symbol):
            raise TradeRejected(f"[WALL5-FAIL] Weekend Blackout active for {signal.symbol}.")

        # 2. Margin Pre-Validation
        acc = mt5.account_info()
        if acc:
            if acc.margin_level > 0 and acc.margin_level < 200.0:
                raise TradeRejected(f"[WALL5-FAIL] Margin level too low ({acc.margin_level:.1f}%).")

        # 3. Call check_event_horizon_blackout as a hard gate
        self.check_event_horizon_blackout(signal)

        # 4. Call check_risk_agent check
        self.check_risk_agent(signal, lot_size, price)

        # 5. Return unmodified lot_size if everything passes
        return lot_size
