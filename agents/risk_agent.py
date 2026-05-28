"""
risk_agent.py - PORTFOLIO GUARDIAN (v28.16 — MCP Microservice)
The sovereign risk-management layer. Overrides all other agents.

v28.16 Architecture:
  - Dynamic Portfolio Heat Matrix (4% single-currency correlation cap).
  - Exposed as a FastAPI microservice on port 8001.
  - The Hermes Orchestrator can call /check_trade and /status asynchronously.
"""

import os
import time
import logging
import sys
import datetime
import json
import MetaTrader5 as mt5
from typing import Tuple, Dict
from pathlib import Path

logger = logging.getLogger("RiskAgent")

# ── Level 40 SRE: Economic & Earnings Calendar (v26.3) ──────────────────────
STATIC_MACRO_CALENDAR = {
    "USD": [
        (2, 14, 0, "FOMC Rate Decision"), # Wed 2:00 PM EST
        (4, 8, 30, "Non-Farm Payrolls (NFP)"), # Fri 8:30 AM EST
        (3, 8, 30, "CPI / Inflation Data")
    ],
    "EUR": [
        (3, 8, 15, "ECB Rate Decision")
    ],
    "GBP": [
        (3, 7, 0, "BOE Rate Decision")
    ],
    "AAPL": [(3, 16, 0, "AAPL Q3 Earnings")],
    "MSFT": [(1, 16, 0, "MSFT Q3 Earnings")]
}

def check_upcoming_tier1_events(symbol: str, threshold_hours: float = 24.0) -> Tuple[bool, str]:
    """
    Checks if a Tier-1 macro event or earnings report is scheduled for the given symbol 
    within the next `threshold_hours`. Returns (True, event_name) if event is imminent.
    """
    now = datetime.datetime.utcnow()
    events_to_check = []
    
    if len(symbol) == 6:
        base, quote = symbol[:3], symbol[3:]
        events_to_check.extend(STATIC_MACRO_CALENDAR.get(base, []))
        events_to_check.extend(STATIC_MACRO_CALENDAR.get(quote, []))
    else:
        events_to_check.extend(STATIC_MACRO_CALENDAR.get(symbol, []))
        if "USD" in symbol:
             events_to_check.extend(STATIC_MACRO_CALENDAR.get("USD", []))

    for event in events_to_check:
        e_day, e_hour, e_minute, e_name = event
        days_ahead = e_day - now.weekday()
        if days_ahead < 0 or (days_ahead == 0 and (now.hour > e_hour or (now.hour == e_hour and now.minute > e_minute))):
            days_ahead += 7
            
        event_time = now.replace(hour=e_hour, minute=e_minute, second=0, microsecond=0) + datetime.timedelta(days=days_ahead)
        time_until_event = (event_time - now).total_seconds() / 3600.0
        
        if 0 < time_until_event <= threshold_hours:
            return True, f"{e_name} in {time_until_event:.1f}h"
            
    return False, ""

# ── Dynamic Portfolio Heat Matrix Parsing Helpers (v28.16) ───────────────────

def parse_base_quote(symbol: str) -> Tuple[str, str]:
    """Parses base and quote currencies of the symbol with robust suffix cleaning."""
    sym = symbol.upper().replace(".M", "").replace(".R", "").replace(".T", "").split("-")[0]
    
    # Metal custom overrides
    if sym in ["XAUUSD", "GOLD"]:
        return "XAU", "USD"
    if sym in ["XAGUSD", "SILVER"]:
        return "XAG", "USD"
        
    # Standard G8 / Forex Forex 6-character clean pairs
    if len(sym) == 6 and sym.isalpha():
        return sym[:3], sym[3:]
        
    # Indices & Commodities fallbacks
    if "GER40" in sym or "FRA40" in sym:
        return "EUR", "USD"
    return sym, "USD"

def get_usd_rate(currency: str) -> float:
    """Fetches real-time USD conversion rate for non-USD quotes from MT5 tick ledger."""
    if currency == "USD":
        return 1.0
    # Try Direct Rate (e.g. GBPUSD)
    tick = mt5.symbol_info_tick(f"{currency}USD")
    if tick and tick.bid > 0:
        return tick.bid
    # Try Inverse Rate (e.g. USDJPY)
    tick = mt5.symbol_info_tick(f"USD{currency}")
    if tick and tick.bid > 0:
        return 1.0 / tick.bid
    # Default fallback
    return 1.0

def calculate_currency_exposure(positions) -> Dict[str, float]:
    """
    Parses open symbols and directions to aggregate total risk capital
    deployed against each currency in the G8 basket (converted to USD).
    """
    exposures = {}
    if not positions:
        return exposures
        
    for p in positions:
        try:
            symbol = p.symbol
            base, quote = parse_base_quote(symbol)
            
            # Determine contract size
            sym_info = mt5.symbol_info(symbol)
            contract_size = sym_info.trade_contract_size if sym_info else 100.0
            
            # Calculate risk in quote currency
            if p.sl > 0.0:
                sl_dist = abs(p.price_open - p.sl)
                risk_quote = sl_dist * p.volume * contract_size
            else:
                # Fallback to 2% of notional exposure
                risk_quote = p.volume * p.price_open * contract_size * 0.02
                
            # Convert quote to USD
            rate = get_usd_rate(quote)
            risk_usd = risk_quote * rate
            
            # Aggregate exposures directionally:
            # BUY (type 0): Long Base (+R), Short Quote (-R)
            # SELL (type 1): Short Base (-R), Long Quote (+R)
            if p.type == 0: # BUY
                exposures[base] = exposures.get(base, 0.0) + risk_usd
                exposures[quote] = exposures.get(quote, 0.0) - risk_usd
            else: # SELL
                exposures[base] = exposures.get(base, 0.0) - risk_usd
                exposures[quote] = exposures.get(quote, 0.0) + risk_usd
        except Exception as e:
            logger.warning(f"[RISK_EXPOSURE_ERR] Failed parsing position: {e}")
            
    return exposures

# ── Core RiskAgent Class ─────────────────────────────────────────────────────

class RiskAgent:
    def __init__(self, account_address: str = ""):
        self.address = account_address

        # Risk Parameters (MT5 production calibrated)
        self.max_position_size_usd = 10000.0
        self.max_leverage          = 50
        self.daily_drawdown_limit  = 0.05
        self.total_portfolio_limit = 50000.0
        self.max_symbol_exposure_usd = 20000.0
        self.max_currency_heat_pct  = 0.04  # v28.16 4% Portfolio Correlation Cap

        # State tracking
        self.high_water_mark       = 0.0
        self.circuit_breaker_active = False

    def check_trade(self, symbol: str, size_usd: float, leverage: float, xgb_p: float = 0.5, ddqn_p: float = 0.5) -> Tuple[bool, str]:
        """
        Final check before any order is allowed.
        Includes v23.2 Dissonance Veto, carry tax, ex-ante macro shield,
        and the v28.16 Portfolio Heat 4% single-currency cap.
        """
        if self.circuit_breaker_active:
            return False, "Circuit breaker active. Daily drawdown limit hit."

        # Rule 1.1: ZERO-SIZING VETO
        if size_usd <= 0.0:
            return False, "[ZERO_SIZING_VETO] Sizing is zero."

        # Rule 1.2: AFFORDABILITY VETO Pre-screen for Indices/Metals/Crypto
        if not mt5.initialize():
            logger.error("[RISK_AGENT] MT5 Init failed during pre-screen. Failing safe.")
            return False, "MT5 connection failure in Risk Agent."

        info = mt5.symbol_info(symbol)
        acc = mt5.account_info()
        equity = acc.equity if acc else 1000.0
        if info:
            atr = 0.0010
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 20)
            if rates is not None and len(rates) > 0:
                atr = sum([r['high'] - r['low'] for r in rates]) / len(rates)
            
            point_value = info.trade_tick_value / (info.trade_tick_size / info.point) if info.trade_tick_size > 0 else info.trade_tick_value
            sym_upper = symbol.upper()
            is_indices_metals_crypto = (
                any(idx in sym_upper for idx in ["NAS100", "US30", "SPX500", "SP500", "GER40", "US2000", "HK50"]) or
                any(m in sym_upper for m in ["XAU", "XAG", "GOLD", "SILVER", "XPT", "XPD"]) or
                any(c in sym_upper for c in ["BTC", "ETH", "SOL", "XRP", "LTC", "TRX", "UNI", "DOGE"])
            )
            if is_indices_metals_crypto:
                risk_budget = equity * 0.02
                affordable_lot = risk_budget / (atr * point_value * 3.0 + 1e-12)
                if affordable_lot < info.volume_min:
                    return False, f"[AFFORDABILITY_VETO] Affordable lot {affordable_lot:.4f} < broker min {info.volume_min} for {symbol}."

        MAX_COGNITIVE_DISSONANCE = 0.55
        dissonance = abs(xgb_p - ddqn_p)
        if dissonance > MAX_COGNITIVE_DISSONANCE:
            return False, f"Cognitive Dissonance Exceeded ({dissonance:.2f} > {MAX_COGNITIVE_DISSONANCE:.2f}). XGB: {xgb_p:.2f} vs DDQN: {ddqn_p:.2f}"

        if leverage > self.max_leverage:
            return False, f"Leverage {leverage}x exceeds max allowed {self.max_leverage}x."

        if size_usd > self.max_position_size_usd:
            return False, f"Position size ${size_usd:.2f} exceeds cap ${self.max_position_size_usd}"

        if not mt5.initialize():
            logger.error("[RISK_AGENT] MT5 Init failed during check_trade. Failing safe.")
            return False, "MT5 connection failure in Risk Agent."

        positions = mt5.positions_get()
        
        # 1. Cumulative exposure check
        cumulative_notional = 0.0
        if positions:
            cumulative_notional = sum([p.volume * p.price_open for p in positions if symbol in p.symbol])
        
        if (cumulative_notional + size_usd) > self.max_symbol_exposure_usd:
            return False, f"Cumulative Exposure Cap Reached: ${cumulative_notional:.2f} + ${size_usd:.2f} > ${self.max_symbol_exposure_usd}"

        # 2. Portfolio Heat Veto (v28.16 Rule 7.4)
        acc = mt5.account_info()
        equity = acc.equity if acc else 1000.0
        
        current_exposures = calculate_currency_exposure(positions)
        base, quote = parse_base_quote(symbol)
        
        # Estimate risk of the incoming trade in USD
        new_risk_usd = size_usd * 0.02  # Default to 2% of notional size
        info = mt5.symbol_info(symbol)
        if info:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 20)
            if rates is not None and len(rates) > 0:
                current_atr = sum([r['high'] - r['low'] for r in rates]) / len(rates)
                sl_dist = max(3.0 * current_atr, info.ask * 0.0025)
                new_risk_usd = (sl_dist / info.ask) * size_usd
        # Cap at 2% absolute equity per trade (Wall 4 risk ceiling)
        new_risk_usd = min(new_risk_usd, 0.02 * equity)
        
        direction = "BUY" if xgb_p > 0.5 else "SELL"
        
        # Simulate new exposures
        simulated_exposures = dict(current_exposures)
        if direction == "BUY":
            simulated_exposures[base] = simulated_exposures.get(base, 0.0) + new_risk_usd
            simulated_exposures[quote] = simulated_exposures.get(quote, 0.0) - new_risk_usd
        else:
            simulated_exposures[base] = simulated_exposures.get(base, 0.0) - new_risk_usd
            simulated_exposures[quote] = simulated_exposures.get(quote, 0.0) + new_risk_usd
            
        # Verify 4.0% limit on absolute net exposure of ANY currency
        for cur, exp_usd in simulated_exposures.items():
            abs_exp = abs(exp_usd)
            limit = self.max_currency_heat_pct * equity
            if abs_exp > limit:
                msg = f"[PORTFOLIO_HEAT_VETO] {symbol} blocked. Simulated directional risk on {cur} (${abs_exp:.2f}) breaches 4.0% heat limit (${limit:.2f})."
                logger.warning(msg)
                return False, msg

        # 3. Negative Carry Veto (Swap Filter)
        if info:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 20)
            if rates is not None and len(rates) > 0:
                current_atr = sum([r['high'] - r['low'] for r in rates]) / len(rates)
                zone2_tp_points = (current_atr * 4.0) / (info.point + 1e-12)
                daily_swap = info.swap_long if direction == "BUY" else info.swap_short
                
                logger.info(f"[{symbol}] AUDIT: H1_ATR={current_atr:.5f} | Swap={daily_swap:.2f}")
                
                if daily_swap < 0:
                    projected_cost_7d = abs(daily_swap) * 7
                    if projected_cost_7d > (0.10 * zone2_tp_points):
                        logger.warning(f"[{symbol}] VETO: 7D_Swap_Cost={projected_cost_7d:.2f} > 10%_Zone2_TP={0.10*zone2_tp_points:.2f}")
                        return False, f"Negative Carry Veto: 7-Day Swap Cost ({projected_cost_7d:.2f}) > 10% of Zone 2 TP ({zone2_tp_points * 0.10:.2f})"
        
        # 4. Ex-Ante Macro Blackout (Pre-Event Embargo)
        has_event, event_desc = check_upcoming_tier1_events(symbol, threshold_hours=24.0)
        if has_event:
            logger.warning(f"[MACRO VETO] Rejecting {symbol} entry. Tier-1 Event scheduled in < 24h: {event_desc}")
            return False, f"Ex-Ante Macro Blackout: {event_desc}"

        return True, "Risk check passed."

    def monitor_portfolio(self):
        pass


# ── MCP Server (FastAPI Microservice) ────────────────────────────────────────

def _start_mcp_server():
    """Starts the RiskAgent as a FastAPI MCP microservice on port 8001."""
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
        import uvicorn

        app = FastAPI(title="Sentinel Risk Agent MCP", version="28.16")
        _agent = RiskAgent()

        class TradeCheckRequest(BaseModel):
            symbol: str
            size_usd: float
            leverage: float
            xgb_p: float = 0.5
            ddqn_p: float = 0.5

        @app.get("/status")
        def status():
            return {
                "agent": "risk_agent",
                "version": "v28.16",
                "circuit_breaker": _agent.circuit_breaker_active,
                "max_leverage": _agent.max_leverage,
                "max_position_usd": _agent.max_position_size_usd,
                "max_currency_heat_pct": _agent.max_currency_heat_pct,
                "timestamp": int(time.time()),
            }

        @app.post("/check_trade")
        def check_trade(req: TradeCheckRequest):
            allow, reason = _agent.check_trade(req.symbol, req.size_usd, req.leverage, req.xgb_p, req.ddqn_p)
            if not allow and ("Dissonance" in reason or "Exposure" in reason or "Veto" in reason or "VETO" in reason):
                raise HTTPException(status_code=403, detail=reason)
            return {"allow": allow, "reason": reason, "symbol": req.symbol}

        logger.info("[RISK_AGENT_MCP] Starting on port 8001 (Portfolio Heat & Dissonance active)...")
        uvicorn.run(app, host="0.0.0.0", port=8001)

    except ImportError as e:
        logger.error(f"[RISK_AGENT_MCP] FastAPI/uvicorn not available: {e}. Running in direct-import mode only.")


def calculate_volatility_scalar(symbol: str, current_atr: float) -> float:
    """
    Calculates Daniel Bloch's Target Volatility Position Sizing scalar.
    vol_scalar = BASELINE_ATR / current_atr
    Clamped at 1.0 to prevent scaling up risk in low-volatility environments.
    """
    sym = symbol.upper()
    
    # Define baseline ATRs per asset class
    # Forex Majors (e.g., EURUSD, GBPUSD, USDCHF, USDCAD, AUDUSD, NZDUSD)
    if any(m in sym for m in ["EURUSD", "GBPUSD", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]):
        baseline_atr = 0.0050
    # JPY Forex pairs (price ~100-200)
    elif "JPY" in sym:
        baseline_atr = 0.5000
    # Metals (Gold, Silver)
    elif "XAU" in sym or "GOLD" in sym:
        baseline_atr = 15.0
    elif "XAG" in sym or "SILVER" in sym:
        baseline_atr = 0.35
    # Indices (SP500, US30, NAS100, GER40, HK50, etc.)
    elif any(idx in sym for idx in ["US30", "GER40"]):
        baseline_atr = 150.0
    elif "NAS100" in sym:
        baseline_atr = 100.0
    elif any(idx in sym for idx in ["SP500", "SPX500"]):
        baseline_atr = 30.0
    # Cryptocurrencies
    elif "BTC" in sym:
        baseline_atr = 1200.0
    elif "ETH" in sym:
        baseline_atr = 80.0
    # Default fallback
    else:
        baseline_atr = 0.0050
        
    vol_scalar = baseline_atr / (current_atr + 1e-12)
    # Ensure we don't scale up past 1.0 (protecting max risk)
    return min(1.0, vol_scalar)


if __name__ == "__main__":
    import io as _io
    def _get_utf8_stream():
        if getattr(sys.stdout, 'encoding', '').lower() == 'utf-8':
            return sys.stdout
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            return sys.stdout
        except Exception:
            return _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

    _UTF8_STREAM = _get_utf8_stream()
    os.environ["PYTHONIOENCODING"] = "utf-8"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [RISK_AGENT] %(message)s",
        handlers=[
            logging.StreamHandler(_UTF8_STREAM),
            logging.FileHandler(os.path.join("C:\\sentinel_logs", "risk_agent_v28.log"), encoding="utf-8"),
        ]
    )
    _start_mcp_server()
