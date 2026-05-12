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

def _calculate_macroscopic_atr(symbol: str, timeframe=mt5.TIMEFRAME_M15, period=14) -> float:
    """Calculates ATR using macroscopic M15 bars (Directive 2 v21.3)."""
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
            "atr": float(row["atr"])
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


# ── Immediate Market Close ────────────────────────────────────────────────────
def _market_close(pos) -> bool:
    """
    Closes a position at market immediately — bypasses Virtual SL/TP.
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


# ── Notify via Discord ────────────────────────────────────────────────────────
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
        self._last_regime_check: dict[str, float] = {}
        self._regime_persistence_counter: dict[int, int] = defaultdict(int)
        logger.info("Profit Manager v23.14 online — CADES Architecture ACTIVE.")
        self._run_grandfather_sweep()

    def _run_grandfather_sweep(self):
        """Directive 4: Instantly overwrite old static stops with new CADES boundaries."""
        logger.info("Running Grandfather Retroactive Sweep to apply CADES boundaries...")
        positions = mt5.positions_get()
        if not positions:
            logger.info("No active open positions to grandfather.")
            return
            
        count = 0
        for pos in positions:
            info = mt5.symbol_info(pos.symbol)
            if not info: continue
            digits = info.digits
            
            oracle_data = _get_live_oracle_meta(pos.symbol)
            p_val = oracle_data["conviction"] if oracle_data else 0.80
            direction = "BUY" if pos.type == 0 else "SELL"
            p_entry = max(0.60, min(1.0, p_val if direction == "BUY" else (1.0 - p_val)))
            
            macro_atr = _calculate_macroscopic_atr(pos.symbol)
            if macro_atr <= 0:
                macro_atr = oracle_data["atr"] if oracle_data else (info.ask - info.bid) * 2.0
                
            rates = mt5.copy_rates_from_pos(pos.symbol, mt5.TIMEFRAME_M15, 0, 21)
            price_open = pos.price_open
            
            if rates is not None and len(rates) > 0:
                if direction == "BUY":
                    swing_dist = max(0.0, price_open - float(np.min(rates['low'])))
                else:
                    swing_dist = max(0.0, float(np.max(rates['high'])) - price_open)
            else:
                swing_dist = macro_atr * 2.0
                
            sl_dist = max(1.2 * macro_atr, swing_dist)
            target_sl = price_open - sl_dist if direction == "BUY" else price_open + sl_dist
            target_sl = round(target_sl, digits)
            
            tp_dist = macro_atr * (2.0 + 4.0 * ((p_entry - 0.60) / 0.40))
            target_tp = price_open + tp_dist if direction == "BUY" else price_open - tp_dist
            target_tp = round(target_tp, digits)
            
            logger.info(f"[GRANDFATHER] {pos.symbol} #{pos.ticket} applying CADES: Assumed/Live P={p_entry:.2f} -> SL={target_sl} | TP={target_tp}")
            mod_req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "sl": float(target_sl),
                "tp": float(target_tp),
                "position": pos.ticket
            }
            mod_res = mt5.order_send(mod_req)
            if mod_res and mod_res.retcode == mt5.TRADE_RETCODE_DONE:
                count += 1
                logger.info(f"[GRANDFATHER_OK] Successfully grandfathered #{pos.ticket}.")
            else:
                logger.warning(f"[GRANDFATHER_FAIL] Failed on #{pos.ticket}: retcode={mod_res.retcode if mod_res else 'None'}")
                
        logger.info(f"Grandfather sweep complete. Updated {count}/{len(positions)} positions.")

    # ── PSR (Bailey & Lopez de Prado) ─────────────────────────────────────────
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

    # ── PSR Audit ─────────────────────────────────────────────────────────────
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
            logger.critical(f"⚠️ [PSR_DEGRADATION] PSR={psr_val:.4f} < {PSR_THRESHOLD}")
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
        _notify(f"⚠️ **PSR_DEGRADATION**\nLive PSR = {psr_val:.4f} < {PSR_THRESHOLD}\nSRE halt triggered.")

    # ── Dynamic Regime Liquidation (SRE Phase 6 Patch) ────────────────────────
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
            
            # ── Mechanical Profit Locking (v23.13 Fluid Mechanics) ─────────────────────
            profit_price_delta = current_price - price_open if pos.type == 0 else price_open - current_price
            digits = info.digits if info else 5
            
            # Fat Tail Capture: Hardcode initial physical MT5 Take-Profit to 5.0 * ATR
            target_tp = price_open + (5.0 * macro_atr) if pos.type == 0 else price_open - (5.0 * macro_atr)
            target_tp = round(target_tp, digits)
            
            target_sl = pos.sl
            modify_needed = False
            
            if profit_price_delta >= 2.0 * macro_atr:
                # Zone 3: Parabolic Trail (Current_Price - 1.5 ATR)
                trail_sl = current_price - (1.5 * macro_atr) if pos.type == 0 else current_price + (1.5 * macro_atr)
                trail_sl = round(trail_sl, digits)
                if pos.type == 0 and (target_sl == 0.0 or trail_sl > target_sl):
                    target_sl = trail_sl
                    modify_needed = True
                elif pos.type == 1 and (target_sl == 0.0 or trail_sl < target_sl):
                    target_sl = trail_sl
                    modify_needed = True
            elif profit_price_delta >= 1.75 * macro_atr:
                # Zone 2: Fee-Paid Break-Even (+0.2 ATR)
                be_sl = price_open + (0.2 * macro_atr) if pos.type == 0 else price_open - (0.2 * macro_atr)
                be_sl = round(be_sl, digits)
                if pos.type == 0 and (target_sl == 0.0 or target_sl < be_sl):
                    target_sl = be_sl
                    modify_needed = True
                elif pos.type == 1 and (target_sl == 0.0 or target_sl > be_sl):
                    target_sl = be_sl
                    modify_needed = True
            elif profit_price_delta >= 1.2 * macro_atr:
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
                    "sl": float(target_sl),
                    "tp": float(current_tp),
                    "position": pos.ticket
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
            
            # Directive 3: Dead-Money Time Stop
            is_dead_money = (trade_ticks > 300) and (abs(profit_atr) < 0.25)
            
            # Directive 1: Time Stop (Theta Decay) - v21.4
            MAX_HOLDING_SECONDS = 6 * 3600
            elapsed_seconds = now - pos.time
            is_theta_decay = (elapsed_seconds > MAX_HOLDING_SECONDS) and (pos.profit <= 0)
            
            # Directive 3: Data Density Grace Period Blindfold logic
            if trade_ticks < 100 and (now - pos.time < 600):
                if is_regime_conflict or is_thesis_decay or is_dead_money:
                    logger.info(f"[DATA_DENSITY_GRACE] {symbol} #{pos.ticket} data density low ({trade_ticks} < 100 ticks). Suppressing cognitive exits.")
                    is_regime_conflict = False
                    is_thesis_decay = False
                    is_dead_money = False
            
            if is_velocity_kill or is_dead_money or is_regime_conflict or is_thesis_decay or is_sl_hit or is_tp_hit or is_theta_decay:
                if is_velocity_kill:
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
                logger.warning(f"🚨 [AUTONOMOUS SRE] Liquidated {symbol} due to {reason_type}. PnL={pos.profit:+.2f}")

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
                logger.debug(f"[REGIME_OK] {symbol} #{pos.ticket}: {pos_direction} | HMM={hmm_state} — aligned.")

    # ── Monitor Loop ──────────────────────────────────────────────────────────
    def monitor_loop(self):
        logger.info(
            "Starting monitor loop — PSR audit every 10 min | Position scan every 1 s."
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
                    # Directive 2: Naked Trade Sweep (Retroactive TP Enforcement)
                    for pos in all_positions:
                        if pos.tp == 0.0:
                            info = mt5.symbol_info(pos.symbol)
                            digits = info.digits if info else 5
                            macro_atr = _calculate_macroscopic_atr(pos.symbol)
                            if macro_atr <= 0:
                                tick = mt5.symbol_info_tick(pos.symbol)
                                spread = (tick.ask - tick.bid) if tick else 0.0001
                                macro_atr = spread * 2.0
                            
                            tp_dist = macro_atr * 3.0
                            target_tp = pos.price_open + tp_dist if pos.type == 0 else pos.price_open - tp_dist
                            target_tp = round(target_tp, digits)
                            
                            logger.info(f"[NAKED_SWEEP] {pos.symbol} #{pos.ticket} has TP=0.0. Forcing retroactive Take-Profit to {target_tp}...")
                            mod_req = {
                                "action": mt5.TRADE_ACTION_SLTP,
                                "symbol": pos.symbol,
                                "sl": float(pos.sl),
                                "tp": float(target_tp),
                                "position": pos.ticket,
                                "magic": pos.magic
                            }
                            mod_res = mt5.order_send(mod_req)
                            if mod_res and mod_res.retcode == mt5.TRADE_RETCODE_DONE:
                                logger.info(f"[TP_ENFORCED] Retroactively attached TP={target_tp} to #{pos.ticket} successfully.")
                            else:
                                logger.warning(f"[TP_ENFORCED_FAIL] Failed to attach TP to #{pos.ticket}: retcode={mod_res.retcode if mod_res else 'None'}")

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
