"""
profit_manager.py - ADAPTIVE SENTINEL PROFIT MANAGER & PSR AUDITOR (v17.3)
Constitution: Probabilistic Sharpe Ratio tripwire, virtual stop monitoring, SRE halt.
"""
import MetaTrader5 as mt5
import os
import sys
import time
import json
import socket
import logging
import numpy as np
import pandas as pd
from scipy import stats
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

MAGIC_NUMBER    = 142
PSR_THRESHOLD   = 0.80
DIAG_DIR        = Path("C:/Sentinel_Project/pending_diagnostics")
LOG_DIR         = Path(r"C:\sentinel_logs")
WEBHOOK_URL     = os.getenv("DISCORD_WEBHOOK_URL", "")

for d in (DIAG_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PROFIT_MANAGER] %(message)s",
    force=True,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_DIR / "profit_manager_v17_3.log")),
    ],
)
logger = logging.getLogger("ProfitManager")


def _notify(msg: str):
    if not WEBHOOK_URL:
        return
    try:
        import requests
        requests.post(WEBHOOK_URL, json={"content": msg}, timeout=8)
    except Exception:
        pass


class SentinelProfitManager:
    """
    v17.3: PSR auditor + SRE halt tripwire.
    Monitors live positions against virtual SL/TP anchors.
    """

    def __init__(self):
        if not mt5.initialize():
            logger.critical("[FATAL] MT5 init failed.")
            sys.exit(1)
        logger.info("Profit Manager v17.3 online.")

    # ── PSR (Bailey & Lopez de Prado) ─────────────────────────────────────────
    def calculate_psr(self, returns: list) -> float:
        arr = np.array(returns)
        if len(arr) < 10:
            return 1.0  # insufficient samples — assume healthy
        sharpe    = np.mean(arr) / (np.std(arr) + 1e-9)
        n         = len(arr)
        skew      = stats.skew(arr)
        kurt      = stats.kurtosis(arr)
        std_err   = np.sqrt(
            (1 - skew * sharpe + (kurt - 1) / 4.0 * sharpe ** 2) / max(n - 1, 1)
        )
        psr = float(stats.norm.cdf(sharpe / (std_err + 1e-9)))
        return psr

    # ── PSR Audit ─────────────────────────────────────────────────────────────
    def audit_performance(self):
        """Phase 5: Audits last 7 days of closed deals. Triggers SRE halt if PSR < 0.80."""
        now = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(now - timedelta(days=7), now)
        if not deals:
            return
        returns = [
            d.profit for d in deals
            if d.magic == MAGIC_NUMBER and d.entry == mt5.DEAL_ENTRY_OUT
        ]
        if not returns:
            return
        psr_val = self.calculate_psr(returns)
        logger.info(f"[PSR_AUDIT] Current PSR: {psr_val:.4f} (threshold={PSR_THRESHOLD})")

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

    # ── Monitor Loop ──────────────────────────────────────────────────────────
    def monitor_loop(self):
        logger.info("Starting monitor loop (PSR audit every 10 min, position scan every 1 s).")
        last_audit = 0.0

        while True:
            try:
                # Periodic PSR audit
                if time.time() - last_audit > 600:
                    self.audit_performance()
                    last_audit = time.time()

                # Position heartbeat (virtual stop logic lives in BrawnExecutor on VPS;
                # here we just log live exposure for telemetry)
                positions = mt5.positions_get(magic=MAGIC_NUMBER) or []
                for pos in positions:
                    tick = mt5.symbol_info_tick(pos.symbol)
                    if not tick:
                        continue
                    current = tick.bid if pos.type == 0 else tick.ask
                    pnl_pct = (current - pos.price_open) / (pos.price_open + 1e-9)
                    if pos.type == 1:  # SELL
                        pnl_pct = -pnl_pct
                    logger.debug(f"[{pos.symbol}] PnL%: {pnl_pct:.3%} | Ticket #{pos.ticket}")

                time.sleep(1)
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(10)


if __name__ == "__main__":
    # Singleton
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
