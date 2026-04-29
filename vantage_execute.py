"""
vantage_execute.py - ADAPTIVE SENTINEL EXECUTION NODE (v17.3 Decoupled Production Build)
Machine B (Oracle VPS) ONLY.
Responsibilities:
  • Listen for JSON signals via Discord Bridge
  • Validate: Amnesia Lock, Weekend Blackout, Portfolio Heat, Kelly sizing
  • Execute market orders with NO hard SL/TP (pure virtual stops)
  • Run high-frequency (0.5 s) tick monitor for virtual SL/TP breach detection
"""
import MetaTrader5 as mt5
import os
import time
import json
import socket
import sys
import threading
import logging
import requests
import discord
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone, time as dt_time
from typing import Dict, Any, Optional

# ── Bootstrap ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.resolve()
load_dotenv(PROJECT_ROOT / ".env")

DISCORD_BOT_TOKEN  = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
WEBHOOK_URL        = os.getenv("DISCORD_WEBHOOK_URL", "")
MAGIC_NUMBER       = 142

# ── Config (mirrors sentinel_config.py — no import dep on Machine A modules) ──
KELLY_FRACTION      = 0.25
PORTFOLIO_HEAT_CAP  = 0.20   # 20 %
HARD_RISK_CAP       = 0.02   # 2.0 % per trade
LEVERAGE_WALL       = 10.0   # 10× equity
EPISTEMIC_GATE      = 0.82
MIN_LOT             = 0.01   # Broker minimum micro-lot

# ── Logging ───────────────────────────────────────────────────────────────────
log_file = PROJECT_ROOT / "vantage_execute_brawn.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EXECUTION_NODE] %(message)s",
    force=True,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file)),
    ],
)
logger = logging.getLogger("VantageExecute")

sys.path.append(str(PROJECT_ROOT))
import gitagent_sigproc as sigproc
import gitagent_utils as utils

# ── Helpers ───────────────────────────────────────────────────────────────────

def _notify(msg: str):
    if not WEBHOOK_URL:
        return
    try:
        requests.post(WEBHOOK_URL, json={"content": msg}, timeout=8)
    except Exception as e:
        logger.error(f"Notification error: {e}")

def _is_weekend_blackout(symbol: str) -> bool:
    """
    Phase 4: Friday 23:55 → Monday 00:15 broker time blackout.
    Crypto (detected by regime) runs 24/7.
    """
    regime = utils.get_symbol_regime(symbol)
    if regime == "CRYPTO":
        return False  # Crypto never blocked

    now_utc = datetime.now(timezone.utc)
    wd = now_utc.weekday()  # Mon=0 … Sun=6
    t  = now_utc.time()

    # Friday after 21:55 UTC ≈ 23:55 broker (UTC+2)
    if wd == 4 and t >= dt_time(21, 55):
        return True
    # All of Saturday
    if wd == 5:
        return True
    # Sunday before 22:15 UTC ≈ 00:15 Monday broker
    if wd == 6 and t <= dt_time(22, 15):
        return True
    return False

def _get_cat_multiplier(symbol: str) -> float:
    regime = utils.get_symbol_regime(symbol)
    if regime in ("FOREX_USD", "FOREX_CROSS"):
        return 12.0
    if regime in ("INDEX", "COMMODITY", "CRYPTO"):
        return 8.0
    if regime == "EQUITY":
        return 6.0
    return 8.0

# ── Kelly Sizing (Phase 4 — Fractional Kelly) ─────────────────────────────────

def calculate_kelly_lot(symbol: str, p: float, atr: float, info) -> float:
    """
    Phase 4: f* = p - (q / b), scaled by KELLY_FRACTION = 0.25.
    Enforces Hard Risk Cap (2 %), Portfolio Heat (20 %), Leverage Wall (10×).
    Small-account bypass: rounds up to MIN_LOT if 0 < lot < MIN_LOT.
    """
    acc = mt5.account_info()
    if not acc:
        return 0.0

    equity   = acc.equity
    q        = 1.0 - p
    b        = 2.0  # reward:risk ratio assumption (2:1)
    f_raw    = max(0.0, p - (q / b))
    f_kelly  = f_raw * KELLY_FRACTION

    # Absolute ceilings
    f_kelly = min(f_kelly, HARD_RISK_CAP)

    # Portfolio heat ceiling
    open_pos = mt5.positions_get() or []
    used_margin = sum(pos.margin_initial for pos in open_pos)
    heat = used_margin / equity if equity > 0 else 0
    if heat >= PORTFOLIO_HEAT_CAP:
        logger.warning(f"[{symbol}] Portfolio Heat {heat:.1%} >= {PORTFOLIO_HEAT_CAP:.0%}. Sizing blocked.")
        return 0.0

    # Leverage wall
    total_exposure = sum(pos.price_open * pos.volume * info.trade_contract_size for pos in open_pos)
    if total_exposure > equity * LEVERAGE_WALL:
        logger.warning(f"[{symbol}] Leverage Wall breached. Sizing blocked.")
        return 0.0

    # Risk-in-money → lot
    risk_usd  = equity * f_kelly
    cat_dist  = atr * _get_cat_multiplier(symbol)
    min_dist  = max(info.trade_stops_level * info.point, 2 * (info.ask - info.bid))
    cat_dist  = max(cat_dist, min_dist)

    tick_val  = info.trade_tick_value
    tick_size = info.trade_tick_size
    point_val = tick_val / (tick_size / info.point)

    lot = risk_usd / (cat_dist * point_val + 1e-9)
    lot = round(lot / info.volume_step) * info.volume_step
    lot = max(info.volume_min, min(lot, info.volume_max))

    # Small-account bypass
    if 0.0 < lot < MIN_LOT:
        logger.warning(
            f"[{symbol}] [HARD_RISK_CAP_WARN] Calculated lot {lot:.4f} < MIN_LOT {MIN_LOT}. "
            f"Rounding UP to {MIN_LOT} to allow signal execution."
        )
        lot = MIN_LOT

    return float(lot)

# ── Execution Core ────────────────────────────────────────────────────────────

class BrawnExecutor:
    """Pure execution daemon. Receives validated signals, manages virtual stops."""

    def __init__(self):
        if not mt5.initialize():
            logger.error("[FATAL] MT5 init failed inside WINE.")
            sys.exit(1)
        self.virtual_stops: Dict[int, dict] = {}
        self.lock = threading.Lock()
        threading.Thread(target=self._tick_monitor, daemon=True).start()
        logger.info("BrawnExecutor online. Virtual stop monitor started.")

    # ── Amnesia Lock (Phase 4) ────────────────────────────────────────────────
    def _amnesia_lock(self, symbol: str, direction: str) -> bool:
        """Returns True (blocked) if an open position already exists in the same direction."""
        positions = mt5.positions_get(symbol=symbol) or []
        mt5_dir   = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        for pos in positions:
            if pos.magic == MAGIC_NUMBER and pos.type == mt5_dir:
                logger.warning(f"[AMNESIA_LOCK] {symbol}: existing {direction} position (#{pos.ticket}). Blocking sub-order.")
                return True
        return False

    # ── Route (main entry from Discord bridge) ────────────────────────────────
    def route_signal(self, payload: Dict[str, Any]):
        symbol    = payload.get("symbol", "")
        p         = float(payload.get("kronos_conviction", 0.5))
        hmm_state = payload.get("hmm_state", "RANGE")
        atr       = float(payload.get("atr", 0.001))

        # Phase 4 Gate: conviction must still be >= 0.82 on VPS side
        if p < EPISTEMIC_GATE:
            logger.warning(f"[{symbol}] Conviction {p:.3f} < EPISTEMIC_GATE {EPISTEMIC_GATE}. Rejected.")
            return

        direction = "BUY" if p > 0.5 else "SELL"

        # Phase 2: Regime alignment blocks
        if hmm_state == "BEAR" and direction == "BUY":
            logger.warning(f"[{symbol}] BEAR regime blocks BUY. Rejected.")
            return
        if hmm_state == "BULL" and direction == "SELL":
            logger.warning(f"[{symbol}] BULL regime blocks SELL. Rejected.")
            return

        # Weekend blackout
        if _is_weekend_blackout(symbol):
            logger.warning(f"[{symbol}] Weekend blackout active. Rejected.")
            return

        # Amnesia lock
        if self._amnesia_lock(symbol, direction):
            return

        mt5.symbol_select(symbol, True)
        info = mt5.symbol_info(symbol)
        if not info:
            logger.error(f"[{symbol}] Symbol not found in MT5.")
            return

        lot = calculate_kelly_lot(symbol, p, atr, info)
        if lot <= 0.0:
            logger.warning(f"[{symbol}] Zero lot size computed. Aborting.")
            return

        price     = info.ask if direction == "BUY" else info.bid
        cat_dist  = max(atr * _get_cat_multiplier(symbol),
                        max(info.trade_stops_level * info.point, 2 * (info.ask - info.bid)))
        virtual_sl = (price - cat_dist) if direction == "BUY" else (price + cat_dist)
        virtual_tp = (price + cat_dist * 2.0) if direction == "BUY" else (price - cat_dist * 2.0)

        # Phase 5: NO hard SL/TP on broker (sl=0, tp=0)
        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       lot,
            "type":         mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
            "price":        round(price, info.digits),
            "sl":           0.0,
            "tp":           0.0,
            "magic":        MAGIC_NUMBER,
            "comment":      "BRAWN_v17.3",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        res = mt5.order_send(request)
        if res.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"[{symbol}] Order FAILED: {res.comment} (retcode={res.retcode})")
            return

        ticket = res.order
        with self.lock:
            self.virtual_stops[ticket] = {
                "symbol":    symbol,
                "direction": direction,
                "order_type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
                "volume":    lot,
                "sl":        round(virtual_sl, info.digits),
                "tp":        round(virtual_tp, info.digits),
            }
        logger.info(
            f"[{symbol}] ✅ Executed {direction} {lot} @ {price:.5f} | "
            f"V-SL={virtual_sl:.5f} V-TP={virtual_tp:.5f} (ticket #{ticket})"
        )
        _notify(
            f"**{'🟢' if direction=='BUY' else '🔴'} BRAWN EXECUTION**\n"
            f"**Symbol:** {symbol} | **Action:** {direction}\n"
            f"**Conviction:** {p:.2%} | **Lot:** {lot}\n"
            f"**V-SL:** {virtual_sl:.5f} | **V-TP:** {virtual_tp:.5f}"
        )

    # ── High-Frequency Tick Monitor (0.5 s) ──────────────────────────────────
    def _tick_monitor(self):
        logger.info("[MONITOR] Virtual stop tick monitor active (0.5 s interval).")
        while True:
            try:
                with self.lock:
                    tickets = list(self.virtual_stops.keys())
                for ticket in tickets:
                    with self.lock:
                        if ticket not in self.virtual_stops:
                            continue
                        data = self.virtual_stops[ticket]

                    tick = mt5.symbol_info_tick(data["symbol"])
                    if not tick:
                        continue

                    breached, reason = False, ""
                    if data["order_type"] == mt5.ORDER_TYPE_BUY:
                        if tick.bid <= data["sl"]:
                            breached, reason = True, "V-SL"
                        elif tick.bid >= data["tp"]:
                            breached, reason = True, "V-TP"
                    else:
                        if tick.ask >= data["sl"]:
                            breached, reason = True, "V-SL"
                        elif tick.ask <= data["tp"]:
                            breached, reason = True, "V-TP"

                    if breached:
                        self._market_close(ticket, data, reason)
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"[MONITOR] Error: {e}")
                time.sleep(1.0)

    def _market_close(self, ticket: int, data: dict, reason: str):
        symbol     = data["symbol"]
        close_type = mt5.ORDER_TYPE_SELL if data["order_type"] == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick       = mt5.symbol_info_tick(symbol)
        if not tick:
            return
        price = tick.bid if data["order_type"] == mt5.ORDER_TYPE_BUY else tick.ask
        res = mt5.order_send({
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       float(data["volume"]),
            "type":         close_type,
            "position":     ticket,
            "price":        price,
            "deviation":    20,
            "magic":        MAGIC_NUMBER,
            "comment":      f"V_CLOSE_{reason[:5]}",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        })
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"[{symbol}] {reason} breached @ {price}. Ticket #{ticket} closed.")
            _notify(f"**🛡️ VIRTUAL STOP HIT**\n**{symbol}** | Reason: {reason} | Price: {price} | #{ticket}")
            with self.lock:
                self.virtual_stops.pop(ticket, None)
        else:
            logger.error(f"[{symbol}] Close failed for #{ticket}: {res.comment}")

# ── Discord Bridge ─────────────────────────────────────────────────────────────

class DiscordBridge(discord.Client):
    def __init__(self, executor: BrawnExecutor, channel_id_raw: str):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.executor = executor
        self.channel_id_raw = channel_id_raw
        self.target_channel = None

    async def on_ready(self):
        if self.channel_id_raw.isdigit():
            self.target_channel = self.get_channel(int(self.channel_id_raw))
        else:
            for guild in self.guilds:
                self.target_channel = discord.utils.get(guild.text_channels, name=self.channel_id_raw)
                if self.target_channel:
                    break
        status = self.target_channel.name if self.target_channel else "NOT FOUND"
        logger.info(f"Discord Bridge online as {self.user} | Channel: {status}")

    async def on_message(self, message):
        if not self.target_channel or message.channel.id != self.target_channel.id:
            return
        if message.author == self.user:
            return
        try:
            payload = json.loads(message.content)
            if "symbol" in payload and "kronos_conviction" in payload:
                await message.delete()
                logger.info(f"[ATOMIC] Signal for {payload['symbol']} captured and wiped.")
                threading.Thread(
                    target=self.executor.route_signal, args=(payload,), daemon=True
                ).start()
        except (json.JSONDecodeError, Exception):
            pass

# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Singleton lock
    try:
        _lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock.bind(("127.0.0.1", 65432))
    except socket.error:
        print("[FATAL] Instance already running. Exiting.")
        sys.exit(1)

    logger.info("═" * 60)
    logger.info("  ADAPTIVE SENTINEL EXECUTION NODE v17.3 — Machine B (Brawn)")
    logger.info("═" * 60)

    if not DISCORD_BOT_TOKEN or not DISCORD_CHANNEL_ID:
        logger.error("[FATAL] Discord credentials missing in .env.")
        sys.exit(1)

    executor = BrawnExecutor()
    client   = DiscordBridge(executor, DISCORD_CHANNEL_ID)

    try:
        client.run(DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Shutting down…")
    finally:
        mt5.shutdown()
        sys.exit(0)
