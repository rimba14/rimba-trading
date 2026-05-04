"""
profit_manager.py - ADAPTIVE SENTINEL PROFIT MANAGER & PSR AUDITOR (v19.2)
Constitution: PSR tripwire, Virtual Stop monitoring, SRE halt,
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
from dotenv import load_dotenv
import io

load_dotenv()

MAGIC_NUMBER       = 142
MAGIC_LEGACY       = 17300
PSR_THRESHOLD      = 0.80
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
        logging.FileHandler(str(LOG_DIR / "profit_manager_v19_2.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("ProfitManager")

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
        logger.warning(f"[ORACLE_READ_ERR] {symbol}: {e}")
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
        logger.error(f"[EXIT_SIGNAL] [FAIL] Failed to push exit to HTTP Bridge: {e}")


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
        logger.info("Profit Manager v17.9 online — Dynamic Regime Liquidation ACTIVE | PSR Tripwire ARMED.")

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
        with open(ticket, "w") as fh:
            json.dump(payload, fh, indent=2)
        logger.info(f"[SRE_HALT] Ticket dropped: {ticket.name}")
        _notify(f"⚠️ **PSR_DEGRADATION**\nLive PSR = {psr_val:.4f} < {PSR_THRESHOLD}\nSRE halt triggered.")

    # ── Dynamic Regime Liquidation (SRE Phase 6 Patch) ────────────────────────
    def _regime_liquidation_audit(self, positions: list):
        """
        Polls the live HMM regime for each open position.
        Immediately liquidates any position whose direction conflicts with the regime.

        Liquidation Rule (Constitutional mandate — v17.9 Phase 6):
            BUY  + HMM == BEAR  ->  REGIME_VIOLATION_LIQUIDATION
            SELL + HMM == BULL  ->  REGIME_VIOLATION_LIQUIDATION

        Bypasses Virtual SL/TP. Pushes exit signal to Discord before closing.
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

            pos_direction = "BUY" if pos.type == 0 else "SELL"

            # Directive 2: Thesis-Driven Liquidation (v19.7 Autonomous SRE Patch)
            # Liquidate LONG if P <= 0.48
            # Liquidate SHORT if P >= 0.52
            
            is_violation = False
            if pos_direction == "BUY" and live_p <= 0.48:
                is_violation = True
            elif pos_direction == "SELL" and live_p >= 0.52:
                is_violation = True
            
            if is_violation:
                reason = (
                    f"THESIS_DRIVEN_LIQUIDATION | "
                    f"Live_P={live_p:.4f} | "
                    f"Ticket={pos.ticket} | PnL={pos.profit:+.2f}"
                )
                logger.warning(
                    f"🚨 [AUTONOMOUS SRE] Liquidated {symbol} due to Thesis Decay (P={live_p:.4f}). "
                    f"PnL={pos.profit:+.2f}"
                )

                # Step 1: Push exit signal to Discord (VPS orchestrator awareness)
                _push_exit_signal(pos, reason)

                # Step 2: Execute immediate market close (bypass Virtual SL/TP)
                success = _market_close(pos)
                if success:
                    _LIQUIDATION_COOLDOWN[pos.ticket] = now
                    # Drop SRE diagnostic ticket for audit trail
                    diag = {
                        "event":      "THESIS_DRIVEN_LIQUIDATION",
                        "symbol":     symbol,
                        "ticket":     pos.ticket,
                        "direction":  pos_direction,
                        "hmm_state":  hmm_state,
                        "live_p":     live_p,
                        "pnl":        round(pos.profit, 2),
                        "timestamp":  int(now),
                        "version":    "v17.9-PROD",
                    }
                    diag_path = DIAG_DIR / f"regime_liq_{symbol}_{int(now)}.json"
                    with open(diag_path, "w") as fh:
                        json.dump(diag, fh, indent=2)
                    logger.info(f"[DIAG] SRE ticket written: {diag_path.name}")
            else:
                # ── Virtual SL/TP Tracking (Phase 5 Stabilization) ────────────
                # If thesis is still intact (aligned OR high conviction), check virtual stops.
                try:
                    # hmm_data was already fetched above
                    row = _get_live_hmm_state(symbol) # Refresh for row access if needed or use local
                    # To minimize hits, we reuse hmm_data if possible
                    # But for ATR we need the row again.
                    from arcticdb import Arctic
                    store = Arctic(ARCTIC_DIR)
                    lib   = store["oracle_cache"]
                    item  = lib.read(f"{symbol}_meta")
                    row   = item.data.iloc[-1]
                    atr   = float(row["atr"])
                    
                    price_open = pos.price_open
                    tick = mt5.symbol_info_tick(symbol)
                    if tick:
                        current = tick.bid if pos.type == 0 else tick.ask
                        
                        sl_level = price_open - (SL_ATR_MULT * atr) if pos.type == 0 else price_open + (SL_ATR_MULT * atr)
                        tp_level = price_open + (TP_ATR_MULT * atr) if pos.type == 0 else price_open - (TP_ATR_MULT * atr)
                        
                        is_sl_hit = (pos.type == 0 and current <= sl_level) or (pos.type == 1 and current >= sl_level)
                        is_tp_hit = (pos.type == 0 and current >= tp_level) or (pos.type == 1 and current <= tp_level)
                        
                        if is_sl_hit or is_tp_hit:
                            reason = "VIRTUAL_SL_HIT" if is_sl_hit else "VIRTUAL_TP_HIT"
                            logger.info(f"[VIRTUAL_EXIT] {symbol} #{pos.ticket} hit {reason}. Price={current:.5f}, Level={sl_level if is_sl_hit else tp_level:.5f}")
                            _push_exit_signal(pos, reason)
                            _market_close(pos)
                            continue

                except Exception as e:
                    logger.debug(f"[VIRTUAL_STOP_ERR] {symbol}: {e}")

                logger.debug(f"[REGIME_OK] {symbol} #{pos.ticket}: {pos_direction} | HMM={hmm_state} — aligned.")

    # ── Monitor Loop ──────────────────────────────────────────────────────────
    def monitor_loop(self):
        logger.info(
            "Starting monitor loop — "
            "PSR audit every 10 min | "
            f"Position scan every 1 s | "
            f"Regime liquidation poll every {REGIME_POLL_INTERVAL}s per symbol."
        )
        last_audit = 0.0

        while True:
            try:
                # 1. Periodic PSR audit (every 10 min)
                if time.time() - last_audit > 600:
                    self.audit_performance()
                    last_audit = time.time()

                # 2. Fetch all open positions (Sentinel + legacy magic numbers)
                sentinel_pos = mt5.positions_get(magic=MAGIC_NUMBER)  or []
                legacy_pos   = mt5.positions_get(magic=MAGIC_LEGACY)  or []
                all_positions = list(sentinel_pos) + list(legacy_pos)

                if all_positions:
                    # 3. Dynamic Regime Liquidation Audit (SRE Phase 6)
                    self._regime_liquidation_audit(all_positions)

                    # 4. Telemetry heartbeat (PnL logging for dashboarding)
                    for pos in all_positions:
                        tick = mt5.symbol_info_tick(pos.symbol)
                        if not tick:
                            continue
                        current = tick.bid if pos.type == 0 else tick.ask
                        pnl_pct = (current - pos.price_open) / (pos.price_open + 1e-9)
                        if pos.type == 1:  # SELL
                            pnl_pct = -pnl_pct
                        logger.debug(
                            f"[{pos.symbol}] #{pos.ticket} | "
                            f"PnL%: {pnl_pct:.3%} | Cash: {pos.profit:+.2f} USD"
                        )

                time.sleep(60)

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(10)


if __name__ == "__main__":
    # Singleton guard
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
