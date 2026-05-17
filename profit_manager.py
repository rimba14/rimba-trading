"""
profit_manager.py - ADAPTIVE SENTINEL PROFIT MANAGER & PSR AUDITOR (v23.2)
Constitution: Decoupled Volatility, Spread Guard, Virtual Stop monitoring,
              Dynamic Regime Liquidation (Phase 5 Constitution + Phase 6 SRE Patch).
"""
import MetaTrader5 as mt5
import os
import sys
import time
import json
import socket
import logging
import requests
import numpy as np
from scipy import stats
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from dotenv import load_dotenv
import io

from agents.risk_agent import check_upcoming_tier1_events

load_dotenv()

MAGIC_NUMBER       = 142
MAGIC_LEGACY       = 17300
PSR_THRESHOLD      = 0.80
PSR_EPOCH          = 1778483123 # v19.2 Phase 5 SRE Reset
WEBHOOK_URL        = os.getenv("DISCORD_WEBHOOK_URL")
DIAG_DIR           = Path("C:/Sentinel_Project/pending_diagnostics")
LOG_DIR            = Path(r"C:\sentinel_logs")
ARCTIC_DIR         = "lmdb://C:/Sentinel_Project/data/arctic_cache"

for d in (DIAG_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PROFIT_MANAGER] %(message)s",
    force=True,
    handlers=[
        logging.StreamHandler(io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")),
        logging.FileHandler(str(LOG_DIR / "profit_manager_v20_4.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("ProfitManager")

def _calculate_macroscopic_atr(symbol: str, timeframe=mt5.TIMEFRAME_H1, period=14) -> float:
    """Calculates ATR using macroscopic H1 bars (Directive 2 v26.0 - Level 35 SRE)."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, period + 1)
    if rates is None or len(rates) < period + 1:
        return 0.0
    
    high = rates['high']
    low = rates['low']
    close = rates['close']
    
    tr = np.zeros(period)
    for i in range(period):
        h_l = high[i+1] - low[i+1]
        h_pc = abs(high[i+1] - close[i])
        l_pc = abs(low[i+1] - close[i])
        tr[i] = max(h_l, h_pc, l_pc)
    
    return float(np.mean(tr))

def enforce_stoplevel_and_normalize(symbol, current_price, target_price, is_sl, is_buy):
    """v25.1: Level 29 SRE Stoplevel Armor & Tick Normalization."""
    info = mt5.symbol_info(symbol)
    if not info: return target_price
    
    tick_size = info.trade_tick_size
    point = info.point
    stoplevel_distance = info.trade_stops_level * point
    
    if is_buy:
        if is_sl:
            max_allowed_sl = current_price - stoplevel_distance
            target_price = min(target_price, max_allowed_sl)
        else:
            min_allowed_tp = current_price + stoplevel_distance
            target_price = max(target_price, min_allowed_tp)
    else: # SELL
        if is_sl:
            min_allowed_sl = current_price + stoplevel_distance
            target_price = max(target_price, min_allowed_sl)
        else:
            max_allowed_tp = current_price - stoplevel_distance
            target_price = min(target_price, max_allowed_tp)
            
    normalized_price = round(target_price / tick_size) * tick_size
    return round(normalized_price, info.digits)

def _get_live_oracle_meta(symbol: str) -> dict | None:
    """Reads the latest oracle metadata (HMM, conviction, ATR) from ArcticDB."""
    try:
        from arcticdb import Arctic
        store = Arctic(ARCTIC_DIR)
        lib   = store["oracle_cache"]
        item  = lib.read(f"{symbol}_meta")
        row   = item.data.iloc[-1]
        return {
            "hmm_state": str(row["hmm_state"]),
            "conviction": float(row["meta_conviction"]),
            "atr": float(row["atr"]),
            "entropy": float(row.get("entropy", 0.0))
        }
    except Exception as e:
        import traceback
        logger.warning(f"[ORACLE_READ_ERR] {symbol}: {e}\n{traceback.format_exc()}")
        return None

def _push_exit_signal(pos, reason: str):
    """
    Direct ultra-low-latency execution bridge (Phase 5).
    Constitution v19.1: Discord is strictly prohibited.
    Pushes exit signal to the Execution Node (Machine B).
    """
    url = os.getenv("EXECUTION_ENDPOINT_URL")
    if not url:
        logger.error("[EXIT_SIGNAL] EXECUTION_ENDPOINT_URL not found in .env.")
        return

    payload = {
        "action": "CLOSE",
        "symbol": pos.symbol,
        "ticket": pos.ticket,
        "reason": reason,
        "timestamp": int(time.time()),
    }
    
    try:
        # Pushing to the /liquidate endpoint of fastapi_sniper.py
        resp = requests.post(f"{url}/liquidate", json=payload, timeout=5)
        if resp.status_code == 200:
            logger.info(f"[EXIT_SIGNAL] [OK] Exit command delivered to Execution Node for {pos.symbol} #{pos.ticket}.")
        else:
            logger.error(f"[EXIT_SIGNAL] [FAIL] Execution Node rejected exit: {resp.status_code}")
    except Exception as e:
        import traceback
        logger.error(f"[EXIT_SIGNAL] [FAIL] Failed to push exit to HTTP Bridge: {e}\n{traceback.format_exc()}")


#  Immediate Market Close 
def _market_close(pos) -> bool:
    """
    Closes a position at market immediately  bypasses Virtual SL/TP.
    Returns True on success.
    """
    tick = mt5.symbol_info_tick(pos.symbol)
    if not tick:
        logger.error(f"[CLOSE_ERR] No tick for {pos.symbol}.")
        return False

    close_type  = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    close_price = tick.bid            if pos.type == 0 else tick.ask

    request = {
        "action":      mt5.TRADE_ACTION_DEAL,
        "symbol":      pos.symbol,
        "volume":      pos.volume,
        "type":        close_type,
        "position":    pos.ticket,
        "price":       close_price,
        "deviation":   30,
        "magic":       MAGIC_NUMBER,
        "comment":     "REGIME_VIOLATION_LIQUIDATION",
        "type_time":   mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(request)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(
            f"[LIQUIDATED] {pos.symbol} #{pos.ticket} | {'+' if pos.profit >= 0 else ''}"
            f"{pos.profit:.2f} USD | REGIME_VIOLATION_LIQUIDATION"
        )
        return True
    else:
        code = res.retcode if res else "N/A"
        msg  = res.comment if res else "no response"
        logger.error(f"[CLOSE_FAIL] {pos.symbol} #{pos.ticket} | retcode={code} | {msg}")
        return False


#  Notify via Discord 
def _notify(msg: str):
    if not WEBHOOK_URL:
        return
    try:
        requests.post(WEBHOOK_URL, json={"content": msg}, timeout=8)
    except Exception:
        pass


_LIQUIDATION_COOLDOWN = {}
_POSITION_EXTREMES: dict[int, float] = {}
_CONVICTION_HISTORY: dict[int, list[float]] = defaultdict(list)
_THESIS_DECAY_STREAK: dict[int, int] = defaultdict(int)
_SCALED_OUT_POSITIONS: set[int] = set()
LIQUIDATION_COOLDOWN_S = 60.0
REGIME_POLL_INTERVAL = 5.0

class SentinelProfitManager:
    """
    v17.9: PSR auditor + SRE halt tripwire + Dynamic Regime Liquidation.

    Regime Liquidation (SRE Phase 6 Patch):
      - Polls ArcticDB HMM state every REGIME_POLL_INTERVAL seconds per symbol.
      - Immediately liquidates positions where direction conflicts with live regime.
      - Pushes exit payload to Discord Bridge before closing (Oracle VPS awareness).
    """

    def __init__(self):
        if not mt5.initialize():
            logger.critical("[FATAL] MT5 init failed.")
            sys.exit(1)
            
        try:
            from sentinel_config import WATCHLIST
            for sym in WATCHLIST:
                mt5.symbol_select(sym, True)
        except Exception:
            pass
            
        self._last_regime_check: dict[str, float] = {}
        self._regime_persistence_counter: dict[int, int] = defaultdict(int)
        logger.info("Profit Manager v24.2 online  Continuous Ironclad CADES Naked Sweep ACTIVE.")

    #  PSR (Bailey & Lopez de Prado) 
    def calculate_psr(self, returns: list) -> float:
        arr = np.array(returns)
        if len(arr) < 10:
            return 1.0
        sharpe  = np.mean(arr) / (np.std(arr) + 1e-9)
        n       = len(arr)
        skew    = stats.skew(arr)
        kurt    = stats.kurtosis(arr)
        std_err = np.sqrt(
            (1 - skew * sharpe + (kurt - 1) / 4.0 * sharpe ** 2) / max(n - 1, 1)
        )
        return float(stats.norm.cdf(sharpe / (std_err + 1e-9)))

    #  PSR Audit 
    def audit_performance(self):
        """Phase 5: Audits last 7 days of closed deals. Triggers SRE halt if PSR < 0.80."""
        now   = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(now - timedelta(days=7), now)
        if not deals:
            return
        returns = [
            d.profit for d in deals
            if d.magic in (MAGIC_NUMBER, MAGIC_LEGACY) 
            and d.entry == mt5.DEAL_ENTRY_OUT
            and d.time >= PSR_EPOCH
        ]
        if not returns:
            return
        psr_val = self.calculate_psr(returns)
        logger.info(f"[PSR_AUDIT] PSR={psr_val:.4f} (threshold={PSR_THRESHOLD})")
        if psr_val < PSR_THRESHOLD:
            logger.critical(f" [PSR_DEGRADATION] PSR={psr_val:.4f} < {PSR_THRESHOLD}")
            self._sre_halt(psr_val)

    def _sre_halt(self, psr_val: float):
        payload = {
            "error_type": "PSR_DEGRADATION",
            "psr_value":  round(psr_val, 6),
            "timestamp":  int(time.time()),
            "status":     "HALTED",
            "reason":     f"Live PSR {psr_val:.4f} below {PSR_THRESHOLD}",
        }
        ticket = DIAG_DIR / f"psr_fail_{int(time.time())}.json"
        from filelock import FileLock
        lock_path = str(ticket) + ".lock"
        with FileLock(lock_path):
            with open(ticket, "w") as fh:
                json.dump(payload, fh, indent=2)
        logger.info(f"[SRE_HALT] Ticket dropped: {ticket.name}")
        _notify(f" **PSR_DEGRADATION**\nLive PSR = {psr_val:.4f} < {PSR_THRESHOLD}\nSRE halt triggered.")

    #  Dynamic Regime Liquidation (SRE Phase 6 Patch) 
    def _regime_liquidation_audit(self, positions: list):
        """
        Polls the live HMM regime for each open position.
        Immediately liquidates any position whose direction conflicts with the regime.
        """
        now = time.time()

        for pos in positions:
            symbol = pos.symbol

            # Rate-limit: only poll ArcticDB every REGIME_POLL_INTERVAL seconds per symbol
            last_check = self._last_regime_check.get(symbol, 0.0)
            if now - last_check < REGIME_POLL_INTERVAL:
                continue
            self._last_regime_check[symbol] = now

            # Cooldown: prevent rapid re-triggering on the same ticket
            last_liq = _LIQUIDATION_COOLDOWN.get(pos.ticket, 0.0)
            if now - last_liq < LIQUIDATION_COOLDOWN_S:
                continue

            # Read live HMM state and thesis (conviction) from ArcticDB
            oracle_data = _get_live_oracle_meta(symbol)
            if oracle_data is None:
                continue  # Stale or unavailable - skip
            
            hmm_state = oracle_data["hmm_state"]
            live_p    = oracle_data["conviction"]
            atr       = oracle_data["atr"]

            pos_direction = "BUY" if pos.type == 0 else "SELL"
            price_open = pos.price_open
            
            # Fetch live price for Virtual Stops
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                continue
            current_price = tick.bid if pos.type == 0 else tick.ask
            
            # Define Risk Multipliers locally (Sentinel Standard v20.4)
            symbol_up = symbol.upper()
            if symbol_up in ["GER40", "NAS100", "SP500", "US30", "UK100", "FRA40", "AUS200", "STOXX50"]:
                SL_ATR_MULT = 4.0
                TP_ATR_MULT = 8.0
            elif symbol_up in ["BTCUSD", "ETHUSD", "LTCUSD", "BCHUSD", "ADAUSD", "XRPUSD", "SOLUSD", "XAUUSD", "XAGUSD"]:
                SL_ATR_MULT = 4.0
                TP_ATR_MULT = 8.0
            elif len(symbol_up) == 6 and symbol_up[-3:] in ["USD", "EUR", "JPY", "GBP", "CHF", "AUD", "CAD", "NZD"]:
                SL_ATR_MULT = 6.0
                TP_ATR_MULT = 12.0
            else:
                SL_ATR_MULT = 3.0
                TP_ATR_MULT = 6.0
            
            # Directive: Asymmetric Regime Risk (v20.4)
            if hmm_state == "BULL":
                SL_ATR_MULT *= 0.8
                TP_ATR_MULT *= 1.2
            elif hmm_state == "BEAR":
                SL_ATR_MULT *= 1.2
                TP_ATR_MULT *= 0.8
            
            # Directive 2: Decoupled Volatility Anchoring (v21.3)
            macro_atr = _calculate_macroscopic_atr(symbol)
            if macro_atr <= 0:
                macro_atr = atr # Fallback if M15 fetch fails
            
            # Directive 3: Spread Sanity Guard (v21.3)
            info = mt5.symbol_info(symbol)
            spread = (info.ask - info.bid) if info else 0.0
            
            # Mathematical Fix: actively push VSL at least 1.5x live spread away by adding it to the ATR
            sl_distance = (SL_ATR_MULT * macro_atr) + (spread * 1.5)
            
            min_stop_distance = spread * 1.5
            if sl_distance < min_stop_distance:
                sl_distance = min_stop_distance
                logger.info(f"[{symbol}] Spread Guard Active: VSL forced to {sl_distance:.5f} (1.5x spread)")
            
            sl_level = price_open - sl_distance if pos.type == 0 else price_open + sl_distance
            tp_level = price_open + (TP_ATR_MULT * macro_atr) if pos.type == 0 else price_open - (TP_ATR_MULT * macro_atr)
            
            # Track position price extreme since entry
            pos_ext = _POSITION_EXTREMES.get(pos.ticket, price_open)
            if pos.type == 0:
                pos_ext = max(pos_ext, current_price)
            else:
                pos_ext = min(pos_ext, current_price)
            _POSITION_EXTREMES[pos.ticket] = pos_ext
            
            #  Mechanical Profit Locking (v23.13 Fluid Mechanics) 
            profit_price_delta = current_price - price_open if pos.type == 0 else price_open - current_price
            digits = info.digits if info else 5
            
            # Fat Tail Capture: Hardcode initial physical MT5 Take-Profit to 5.0 * ATR
            target_tp = price_open + (5.0 * macro_atr) if pos.type == 0 else price_open - (5.0 * macro_atr)
            target_tp = round(target_tp, digits)
            
            target_sl = pos.sl
            modify_needed = False
            
            active_regime = hmm_state
            if active_regime == "RANGE":
                # Directive 2: Entropy-Discounted Zone 2 Threshold
                s_ent = oracle_data.get("entropy", 0.0)
                zone_2_limit = 4.0  # v26.0: Widened from 1.75 -> 4.0 ATR for swing
                if s_ent > 0.90:
                    zone_2_limit = 3.4  # 15% Entropy Discount applied
                    logger.info(f"[{symbol}] High Entropy detected ({s_ent:.2f} > 0.90). Discounting Zone 2 to {zone_2_limit}x ATR.")

                if profit_price_delta >= zone_2_limit * macro_atr:
                    # Modify Zone 2: forcefully liquidate 75% of the position volume to capture mean-reverting profits
                    if pos.ticket not in _SCALED_OUT_POSITIONS:
                        logger.info(f"[RANGE_SCALE_OUT] {symbol} #{pos.ticket} active_regime is RANGE and profit >= {zone_2_limit} ATR. Liquidating 75% volume.")
                        _SCALED_OUT_POSITIONS.add(pos.ticket)
                        close_vol = round(pos.volume * 0.75 / info.volume_step) * info.volume_step if info else pos.volume * 0.75
                        if close_vol >= (info.volume_step if info else 0.01):
                            close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
                            close_price = tick.bid if pos.type == 0 else tick.ask
                            scale_req = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "symbol": symbol,
                                "volume": float(close_vol),
                                "type": close_type,
                                "position": pos.ticket,
                                "price": close_price,
                                "deviation": 30,
                                "comment": f"RANGE_SCALE_OUT_75%_S{s_ent:.2f}",
                                "type_time": mt5.ORDER_TIME_GTC,
                                "type_filling": mt5.ORDER_FILLING_IOC,
                            }
                            mt5.order_send(scale_req)
                    
                    # Leave remaining 25% at a Fee-Paid Break-Even (+0.2 ATR)
                    be_sl = price_open + (0.2 * macro_atr) if pos.type == 0 else price_open - (0.2 * macro_atr)
                    be_sl = round(be_sl, digits)
                    if pos.type == 0 and (target_sl == 0.0 or target_sl < be_sl):
                        target_sl = be_sl
                        modify_needed = True
                    elif pos.type == 1 and (target_sl == 0.0 or target_sl > be_sl):
                        target_sl = be_sl
                        modify_needed = True
                elif profit_price_delta >= 2.5 * macro_atr:  # v26.0: Zone 1 widened 1.2 -> 2.5 ATR
                    # Zone 1: Risk Halving (-0.4 ATR from entry)
                    half_sl = price_open - (0.4 * macro_atr) if pos.type == 0 else price_open + (0.4 * macro_atr)
                    half_sl = round(half_sl, digits)
                    if pos.type == 0 and (target_sl == 0.0 or target_sl < half_sl):
                        target_sl = half_sl
                        modify_needed = True
                    elif pos.type == 1 and (target_sl == 0.0 or target_sl > half_sl):
                        target_sl = half_sl
                        modify_needed = True
            else:
                # Original 3-Zone Geometric Trail for non-RANGE regimes
                if profit_price_delta >= 5.0 * macro_atr:  # v26.0: Zone 3 Parabolic activated at +5.0 ATR
                    # Zone 3: Parabolic Trail (Current_Price - 1.5 ATR)
                    trail_sl = current_price - (1.5 * macro_atr) if pos.type == 0 else current_price + (1.5 * macro_atr)
                    trail_sl = round(trail_sl, digits)
                    if pos.type == 0 and (target_sl == 0.0 or trail_sl > target_sl):
                        target_sl = trail_sl
                        modify_needed = True
                    elif pos.type == 1 and (target_sl == 0.0 or trail_sl < target_sl):
                        target_sl = trail_sl
                        modify_needed = True
                elif profit_price_delta >= 4.0 * macro_atr:  # v26.0: Zone 2 widened 1.75 -> 4.0 ATR
                    # Zone 2: Fee-Paid Break-Even (+0.2 ATR)
                    be_sl = price_open + (0.2 * macro_atr) if pos.type == 0 else price_open - (0.2 * macro_atr)
                    be_sl = round(be_sl, digits)
                    if pos.type == 0 and (target_sl == 0.0 or target_sl < be_sl):
                        target_sl = be_sl
                        modify_needed = True
                    elif pos.type == 1 and (target_sl == 0.0 or target_sl > be_sl):
                        target_sl = be_sl
                        modify_needed = True
                elif profit_price_delta >= 2.5 * macro_atr:  # v26.0: Zone 1 widened 1.2 -> 2.5 ATR
                    # Zone 1: Risk Halving (-0.4 ATR from entry)
                    half_sl = price_open - (0.4 * macro_atr) if pos.type == 0 else price_open + (0.4 * macro_atr)
                    half_sl = round(half_sl, digits)
                    if pos.type == 0 and (target_sl == 0.0 or target_sl < half_sl):
                        target_sl = half_sl
                        modify_needed = True
                    elif pos.type == 1 and (target_sl == 0.0 or target_sl > half_sl):
                        target_sl = half_sl
                        modify_needed = True
                    
            current_tp = round(pos.tp, digits)
            if current_tp == 0.0 or abs(current_tp - target_tp) > (info.point * 10 if info else 0.0001):
                current_tp = target_tp
                modify_needed = True
                
            if modify_needed:
                mod_req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "symbol": symbol,
                    "position": pos.ticket,
                    "sl": float(target_sl),
                    "tp": float(pos.tp if pos.tp != 0.0 else current_tp)
                }
                mod_res = mt5.order_send(mod_req)
                if mod_res and mod_res.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(f"[PROFIT_LOCK] {symbol} #{pos.ticket} physically modified: SL={target_sl} | TP={current_tp} (Profit: {profit_price_delta/macro_atr:.2f} ATR)")
                else:
                    logger.warning(f"[PROFIT_LOCK_FAIL] {symbol} #{pos.ticket}: retcode={mod_res.retcode if mod_res else 'None'} | {mod_res.comment if mod_res else ''}")
            
            # Compute absolute thesis agreement conviction score (thesis_p)
            thesis_p = live_p if pos_direction == "BUY" else (1.0 - live_p)
            hist = _CONVICTION_HISTORY[pos.ticket]
            hist.append(thesis_p)
            if len(hist) > 50:
                hist.pop(0)
                
            # Compute 10-period EMA of thesis_p
            ema_p = hist[0]
            alpha = 2.0 / (10.0 + 1.0)
            for val in hist[1:]:
                ema_p = alpha * val + (1.0 - alpha) * ema_p
                
            # Directive 3: Velocity Override (dP/dt)
            is_velocity_kill = False
            if len(hist) >= 3:
                delta_p = hist[-1] - hist[-3]
                if delta_p < -0.30:
                    is_velocity_kill = True
                    logger.warning(f"[{symbol}] Violent Conviction Velocity Drop detected: dP={delta_p:.2f} over last 3 ticks. Triggering immediate [VELOCITY KILL].")
            
            # v24.0 Directive 2: Alternative Data Virtual Exits [MACRO SHOCK] kill switch
            try:
                from gitagent_utils import fetch_unstructured_sentiment
                live_sentiment = fetch_unstructured_sentiment(symbol)
            except Exception:
                live_sentiment = 0.0

            is_macro_shock = False
            if pos_direction == "BUY" and live_sentiment < -0.60:
                is_macro_shock = True
                logger.warning(f"[{symbol}] Alternative Data [MACRO SHOCK] kill switch triggered: Sentiment={live_sentiment:.2f} < -0.60 for Long position.")
            elif pos_direction == "SELL" and live_sentiment > 0.60:
                is_macro_shock = True
                logger.warning(f"[{symbol}] Alternative Data [MACRO SHOCK] kill switch triggered: Sentiment={live_sentiment:.2f} > +0.60 for Short position.")
            
            # Fetch ticks transacted since entry for Data Density logic
            rates_since = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, int(pos.time), int(now) + 60)
            trade_ticks = int(np.sum(rates_since['tick_volume'])) if rates_since is not None else 101

            # Directive 3: Divergence Scale-Out
            if pos.ticket not in _SCALED_OUT_POSITIONS:
                if profit_price_delta >= 2.5 * macro_atr and thesis_p < 0.65:
                    logger.info(f"[SCALE_OUT] {symbol} #{pos.ticket} profit >= 2.5 ATR and conviction weakened ({thesis_p:.2f} < 0.65). Scaling out 50% volume.")
                    _SCALED_OUT_POSITIONS.add(pos.ticket)
                    close_vol = round(pos.volume * 0.5 / info.volume_step) * info.volume_step if info else pos.volume * 0.5
                    if close_vol >= (info.volume_step if info else 0.01):
                        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
                        close_price = tick.bid if pos.type == 0 else tick.ask
                        scale_req = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": symbol,
                            "volume": float(close_vol),
                            "type": close_type,
                            "position": pos.ticket,
                            "price": close_price,
                            "deviation": 30,
                            "comment": "DIVERGENCE_SCALE_OUT_50%",
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC,
                        }
                        scale_res = mt5.order_send(scale_req)
                        if scale_res and scale_res.retcode == mt5.TRADE_RETCODE_DONE:
                            logger.info(f"[SCALE_OUT_OK] Successfully closed {close_vol} lots of #{pos.ticket}.")
                        else:
                            logger.warning(f"[SCALE_OUT_FAIL] Failed to scale out #{pos.ticket}: {scale_res.comment if scale_res else 'None'}")
            
            # Check Virtual Stop Breaches
            is_sl_hit = (pos.type == 0 and current_price <= sl_level) or (pos.type == 1 and current_price >= sl_level)
            is_tp_hit = (pos.type == 0 and current_price >= tp_level) or (pos.type == 1 and current_price <= tp_level)

            # Directive 2: Persistence Gate (v23.2)
            is_regime_conflict = False
            if pos_direction == "BUY" and hmm_state == "BEAR":
                is_regime_conflict = True
            elif pos_direction == "SELL" and hmm_state == "BULL":
                is_regime_conflict = True

            if is_regime_conflict:
                self._regime_persistence_counter[pos.ticket] += 1
                if self._regime_persistence_counter[pos.ticket] < 3:
                    logger.info(f"[PERSISTENCE_GATE] {symbol} #{pos.ticket}: Regime Conflict detected ({hmm_state}), but pending persistence (Count: {self._regime_persistence_counter[pos.ticket]}/3)")
                    is_regime_conflict = False # Defer liquidation
            else:
                self._regime_persistence_counter[pos.ticket] = 0

            # Directive 3: Dynamic Thesis Decay
            tp_atr_dist = abs(pos.tp - price_open) / macro_atr if pos.tp > 0.0 else 4.0
            profit_atr = profit_price_delta / macro_atr
            dynamic_threshold = max(0.15, 0.45 - (max(0.0, profit_atr) / max(0.1, tp_atr_dist)) * 0.30)
            
            if ema_p < dynamic_threshold:
                _THESIS_DECAY_STREAK[pos.ticket] += 1
            else:
                _THESIS_DECAY_STREAK[pos.ticket] = 0
                
            is_thesis_decay = _THESIS_DECAY_STREAK[pos.ticket] >= 3
            
            # ── v26.1: True Swing Time-Stop & Weekend Bypass ──
            # Fetch H1 bars elapsed since entry for the swing time-stop gate
            h1_rates_since = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, int(pos.time), int(now) + 3600)
            h1_candles_elapsed = len(h1_rates_since) if h1_rates_since is not None else 0
            
            crypto_keywords = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOT", "LINK", "AVAX"]
            is_crypto = any(k in symbol.upper() for k in crypto_keywords)
            dt_now = datetime.fromtimestamp(now, tz=timezone.utc)
            
            is_weekend_pause = False
            if not is_crypto:
                if (dt_now.weekday() == 4 and dt_now.strftime('%H:%M') >= "23:55") or \
                   (dt_now.weekday() in [5, 6]) or \
                   (dt_now.weekday() == 0 and dt_now.strftime('%H:%M') < "00:15"):
                    is_weekend_pause = True

            is_dead_money = (h1_candles_elapsed > 72) and (abs(profit_atr) < 0.25) and not is_weekend_pause
            
            # Directive 1: Time Stop (Theta Decay) - v26.0: Extended to 10 days for swing holds
            MAX_HOLDING_SECONDS = 10 * 24 * 3600  # 10 days
            elapsed_seconds = now - pos.time
            is_theta_decay = (elapsed_seconds > MAX_HOLDING_SECONDS) and (pos.profit <= 0)
            
            # Directive 3: Data Density Grace Period Blindfold logic
            if trade_ticks < 100 and (now - pos.time < 600):
                if is_regime_conflict or is_thesis_decay or is_dead_money:
                    logger.info(f"[DATA_DENSITY_GRACE] {symbol} #{pos.ticket} data density low ({trade_ticks} < 100 ticks). Suppressing cognitive exits.")
                    is_regime_conflict = False
                    is_thesis_decay = False
                    is_dead_money = False
            
            if is_macro_shock or is_velocity_kill or is_dead_money or is_regime_conflict or is_thesis_decay or is_sl_hit or is_tp_hit or is_theta_decay:
                if is_macro_shock:
                    reason_type = "[MACRO SHOCK]"
                    trigger_desc = f"Sentiment={live_sentiment:.2f} threshold breached"
                elif is_velocity_kill:
                    reason_type = "[VELOCITY KILL]"
                    trigger_desc = f"dP/dt drop < -0.30 in 3 ticks"
                elif is_dead_money:
                    reason_type = "[DEAD-MONEY STOP]"
                    trigger_desc = f"Ticks={trade_ticks} > 300 | PnL={profit_atr:.2f} ATR"
                elif is_regime_conflict:
                    reason_type = "[REGIME CONFLICT]"
                    trigger_desc = f"{pos_direction} vs {hmm_state}"
                elif is_thesis_decay:
                    reason_type = "[THESIS DECAY]"
                    trigger_desc = f"EMA(P)={ema_p:.4f} < Threshold={dynamic_threshold:.4f}"
                elif is_theta_decay:
                    reason_type = "[TIME STOP / THETA DECAY]"
                    trigger_desc = f"Held {elapsed_seconds/3600:.1f}h | PnL={pos.profit:.2f}"
                elif is_sl_hit:
                    reason_type = "[HARD VIRTUAL STOP]"
                    trigger_desc = f"Price={current_price:.5f} hit SL={sl_level:.5f}"
                else:
                    reason_type = "[THESIS COMPLETE / VTP]"
                    trigger_desc = f"Price={current_price:.5f} hit TP={tp_level:.5f}"

                reason = f"{reason_type} | {trigger_desc} | Ticket={pos.ticket} | PnL={pos.profit:+.2f}"
                logger.warning(f" [AUTONOMOUS SRE] Liquidated {symbol} due to {reason_type}. PnL={pos.profit:+.2f}")

                _push_exit_signal(pos, reason)
                success = _market_close(pos)
                if success:
                    _LIQUIDATION_COOLDOWN[pos.ticket] = now
                    diag = {
                        "event":      reason_type,
                        "symbol":     symbol,
                        "ticket":     pos.ticket,
                        "direction":  pos_direction,
                        "hmm_state":  hmm_state,
                        "live_p":     live_p,
                        "pnl":        round(pos.profit, 2),
                        "timestamp":  int(now),
                        "version":    "v21.3-PROD",
                    }
                    diag_path = DIAG_DIR / f"regime_liq_{symbol}_{int(now)}.json"
                    from filelock import FileLock
                    lock_path = str(diag_path) + ".lock"
                    with FileLock(lock_path):
                        with open(diag_path, "w") as fh:
                            json.dump(diag, fh, indent=2)
                    logger.info(f"[DIAG] SRE ticket written: {diag_path.name}")
            else:
                logger.debug(f"[REGIME_OK] {symbol} #{pos.ticket}: {pos_direction} | HMM={hmm_state}  aligned.")

    def _event_horizon_protection(self, pos) -> bool:
        """v26.3 Level 40 SRE: Pre-Event Risk Reduction.
           Scales out 50% of the position and moves SL to BE if within 12h of Tier-1 Event."""
        if pos.ticket in _SCALED_OUT_POSITIONS:
            return False # Already protected
            
        has_event, event_desc = check_upcoming_tier1_events(pos.symbol, threshold_hours=12.0)
        if not has_event:
            return False
            
        logger.warning(f"[EVENT HORIZON] {pos.symbol} {event_desc}. Scaling out 50% and moving SL to Breakeven to survive gap risk.")
        
        tick = mt5.symbol_info_tick(pos.symbol)
        info = mt5.symbol_info(pos.symbol)
        if not tick or not info:
            return False
            
        # 1. Scale Out 50%
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        close_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        
        # Round volume to step
        half_vol = pos.volume * 0.5
        vol_step = info.volume_step if info.volume_step > 0 else 0.01
        half_vol = max(round(half_vol / vol_step) * vol_step, vol_step)
        
        # Only scale out if the remaining position is >= min volume
        if half_vol < pos.volume:
            request_close = {
                "action":      mt5.TRADE_ACTION_DEAL,
                "symbol":      pos.symbol,
                "volume":      float(half_vol),
                "type":        close_type,
                "position":    pos.ticket,
                "price":       close_price,
                "deviation":   30,
                "magic":       MAGIC_NUMBER,
                "comment":     "EVENT_HORIZON_SCALE_OUT",
                "type_time":   mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            mt5.order_send(request_close)
            
        # 2. Move SL to Breakeven (Fee-Paid BE approx)
        is_buy = (pos.type == mt5.ORDER_TYPE_BUY)
        # Adding a tiny offset for fee-paid BE
        offset = (info.trade_stops_level * info.point) + (info.spread * info.point)
        be_price = pos.price_open + offset if is_buy else pos.price_open - offset
        
        # Ensure we don't worsen the SL
        if (is_buy and be_price > pos.sl) or (not is_buy and be_price < pos.sl and pos.sl > 0):
            # Normalize to avoid 10016
            curr_price = tick.bid if is_buy else tick.ask
            be_price = enforce_stoplevel_and_normalize(pos.symbol, curr_price, be_price, is_sl=True, is_buy=is_buy)
            
            request_mod = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "position": pos.ticket,
                "sl": be_price,
                "tp": pos.tp # Keep TP
            }
            mt5.order_send(request_mod)
            
        _SCALED_OUT_POSITIONS.add(pos.ticket)
        return True

    #  Monitor Loop 
    def monitor_loop(self):
        logger.info(
            "Starting monitor loop  PSR audit every 10 min | Position scan every 1 s."
        )
        last_audit = 0.0
        while True:
            try:
                if time.time() - last_audit > 600:
                    self.audit_performance()
                    last_audit = time.time()

                sentinel_pos = mt5.positions_get(magic=MAGIC_NUMBER)  or []
                legacy_pos   = mt5.positions_get(magic=MAGIC_LEGACY)  or []
                all_positions = list(sentinel_pos) + list(legacy_pos)

                if all_positions:
                    # Directive 3: Continuous Loop Naked Sweep (CADES TP Enforcement)
                    for pos in all_positions:
                        # v26.3 Event Horizon Check
                        self._event_horizon_protection(pos)
                        if pos.tp == 0.0 or pos.sl == 0.0:
                            try:
                                tick = mt5.symbol_info_tick(pos.symbol)
                                if tick is None:
                                    continue
                                
                                # Directive 2: The 10-second Hostile Liquidation Rule (v26.5)
                                time_held = tick.time - pos.time
                                if time_held > 10:
                                    logger.critical(f"[KILL] [NAKED SWEEP] Orphaned trade detected > 10s (Held {time_held}s). Initiating hostile liquidation for Ticket {pos.ticket}.")
                                    _market_close(pos)
                                    continue
                                    
                                info = mt5.symbol_info(pos.symbol)
                                if info is None:
                                    continue
                                    
                                # 1. Force the ATR Magnitude Floor
                                raw_atr = 0.0010 # Fallback baseline
                                price_based_min = pos.price_open * 0.0025 # 0.25% of absolute price
                                broker_min = info.trade_stops_level * info.point
                                true_atr = max(raw_atr, price_based_min, broker_min)
                                
                                # 2. Calculate CADES TP and SL Distances
                                tp_dist = 3.0 * true_atr
                                sl_dist = 1.2 * true_atr
                                
                                # 3. Directional Math
                                if pos.type == mt5.ORDER_TYPE_BUY:
                                    new_tp = pos.price_open + tp_dist
                                    new_sl = pos.price_open - sl_dist
                                elif pos.type == mt5.ORDER_TYPE_SELL:
                                    new_tp = pos.price_open - tp_dist
                                    new_sl = pos.price_open + sl_dist
                                else:
                                    continue
                                    
                                # Preserve existing targets if already attached
                                final_tp = pos.tp if pos.tp > 0.0 else new_tp
                                final_sl = pos.sl if pos.sl > 0.0 else new_sl
 
                                # 4. Universal v25.1 Armor Normalization
                                is_buy = (pos.type == mt5.ORDER_TYPE_BUY)
                                curr_price = tick.bid if is_buy else tick.ask
                                
                                final_sl = enforce_stoplevel_and_normalize(pos.symbol, curr_price, final_sl, is_sl=True, is_buy=is_buy)
                                final_tp = enforce_stoplevel_and_normalize(pos.symbol, curr_price, final_tp, is_sl=False, is_buy=is_buy)
 
                                # Now build the payload...
                                request = {
                                    "action": mt5.TRADE_ACTION_SLTP,
                                    "symbol": pos.symbol,
                                    "position": pos.ticket,
                                    "sl": final_sl,
                                    "tp": final_tp
                                }
                                
                                # 5. Dispatch and Scream on Failure
                                result = mt5.order_send(request)
                                if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                                    err = mt5.last_error()
                                    print(f"[SWEEP REJECTION] Ticket {pos.ticket} ({pos.symbol}) failed SL/TP attach.")
                                    print(f"   -> Retcode: {result.retcode if result else 'None'}, MT5 Error: {err}")
                                    print(f"   -> Attempted TP: {final_tp}, SL: {final_sl}, Open: {pos.price_open}, True ATR: {true_atr}")
                                else:
                                    print(f"[NAKED SWEEP RESCUE] Successfully armored ticket #{pos.ticket} ({pos.symbol}) with normalized SL/TP.")
                                    
                            except Exception as e:
                                print(f"[SWEEP CRASH] Python error during naked sweep for {pos.ticket}: {str(e)}")

                    self._regime_liquidation_audit(all_positions)

                time.sleep(1)

            except Exception as e:
                import traceback
                logger.error(f"Monitor loop error: {e}\n{traceback.format_exc()}")
                time.sleep(10)

if __name__ == "__main__":
    try:
        _lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock.bind(("127.0.0.1", 65436))
    except socket.error:
        print("[FATAL] Profit Manager already running.")
        sys.exit(1)

    mgr = SentinelProfitManager()
    try:
        mgr.monitor_loop()
    except KeyboardInterrupt:
        mt5.shutdown()
