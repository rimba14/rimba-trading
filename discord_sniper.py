import discord
import os
import json
import time
import logging
import sys
import MetaTrader5 as mt5
from datetime import datetime, timezone
from dotenv import load_dotenv
from sentinel_config import WATCHLIST, KELLY_FRACTION, PORTFOLIO_HEAT_CAP, LEVERAGE_WALL, STALENESS_THRESHOLD

# Load environment
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
MAGIC_NUMBER = 142

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SNIPER] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Sniper")

class DiscordSniper(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not mt5.initialize():
            logger.critical("MT5 Initialization failed. Sniper cannot proceed.")
            sys.exit(1)
        logger.info("MT5 Initialized. Sniper online.")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info(f"Monitoring Channel ID: {CHANNEL_ID}")

    async def on_message(self, message):
        # Ignore messages from self or wrong channel
        if message.author == self.user:
            return
        
        # Check if channel ID matches (handle both int and string from env)
        if str(message.channel.id) != str(CHANNEL_ID) and message.channel.name != CHANNEL_ID:
            return

        # Attempt to parse JSON from code blocks
        content = message.content
        if "```json" in content:
            try:
                raw_json = content.split("```json")[1].split("```")[0].strip()
                signal = json.loads(raw_json)
                
                # Check for EXIT signal first
                if signal.get("direction") == "EXIT":
                    await self.process_exit(signal)
                else:
                    await self.process_signal(signal)
            except Exception as e:
                logger.error(f"Failed to parse signal JSON: {e}")

    async def process_exit(self, signal):
        symbol = signal.get("symbol")
        ticket = signal.get("ticket")
        reason = signal.get("reason")
        
        logger.info(f"Received EXIT Signal: {symbol} Ticket {ticket} Reason: {reason}")
        self.execute_exit(ticket, symbol, reason)

    async def process_signal(self, signal):
        symbol = signal.get("symbol")
        direction = signal.get("direction")
        conviction = signal.get("conviction")
        hmm_state = signal.get("hmm_state")
        sig_timestamp = signal.get("timestamp")

        logger.info(f"Received Signal: {symbol} {direction} (P={conviction})")

        # 1. Staleness Check (Phase 1)
        staleness = time.time() - sig_timestamp
        if staleness > STALENESS_THRESHOLD:
            logger.warning(f"[{symbol}] Signal REJECTED: STALE ({staleness:.1f}s old)")
            return

        # 2. Risk Gates (Phase 4)
        if not self.check_risk_gates(symbol, direction, hmm_state):
            return

        # 3. Kelly Sizing (Phase 4)
        lot_size = self.calculate_kelly_lot(symbol, conviction)
        if lot_size <= 0:
            logger.warning(f"[{symbol}] Signal REJECTED: Lot size <= 0")
            return

        # 4. Execution
        self.execute_trade(symbol, direction, lot_size, conviction)

    def check_risk_gates(self, symbol, direction, hmm_state):
        # A. Weekend Protocol
        if self.is_weekend_blackout(symbol):
            logger.warning(f"[{symbol}] Signal REJECTED: Weekend Protocol Blackout")
            return False

        # B. HMM Regime Alignment
        if hmm_state == "BEAR" and direction == "BUY":
            logger.warning(f"[{symbol}] Signal REJECTED: Regime/Direction Mismatch (BEAR/BUY)")
            return False
        if hmm_state == "BULL" and direction == "SELL":
            logger.warning(f"[{symbol}] Signal REJECTED: Regime/Direction Mismatch (BULL/SELL)")
            return False

        # C. Amnesia Lock
        if self.has_active_position(symbol):
            logger.warning(f"[{symbol}] Signal REJECTED: Amnesia Lock Active")
            return False

        # D. Portfolio Heat & Leverage (Simplified for local check)
        acc = mt5.account_info()
        if not acc: return False
        
        # If margin level is > 0 (positions open) and it's below 200, it's unsafe.
        # If margin level is 0.0, it usually means no positions are open, which is safe.
        if acc.margin_level > 0 and acc.margin_level < 200:
             logger.warning(f"[{symbol}] Signal REJECTED: Margin Level too low ({acc.margin_level})")
             return False

        return True

    def is_weekend_blackout(self, symbol):
        # Crypto runs 24/7
        crypto_keywords = ["BTC", "ETH", "BCH", "LTC", "SOL", "XRP", "ADA", "DOGE", "DOT", "LINK", "UNI"]
        if any(k in symbol.upper() for k in crypto_keywords):
            return False
            
        # Broker Time via EURUSD
        tick = mt5.symbol_info_tick("EURUSD")
        if not tick: return False
        
        dt = datetime.fromtimestamp(tick.time, tz=timezone.utc)
        weekday = dt.weekday() # 4=Fri, 0=Mon
        time_str = dt.strftime('%H:%M')
        
        if (weekday == 4 and time_str >= "23:55") or (weekday in [5, 6]) or (weekday == 0 and time_str < "00:15"):
            return True
        return False

    def has_active_position(self, symbol):
        positions = mt5.positions_get(symbol=symbol)
        if positions:
            for p in positions:
                if p.magic == MAGIC_NUMBER:
                    return True
        return False

    def calculate_kelly_lot(self, symbol, conviction):
        info = mt5.symbol_info(symbol)
        acc = mt5.account_info()
        if not info or not acc: return 0.0

        p = abs(conviction - 0.5) + 0.5
        q = 1.0 - p
        b = 1.5 # Win/Loss Ratio assumption
        f_star = p - (q / b)
        f_adj = f_star * KELLY_FRACTION
        
        # Absolute Risk Cap: 2% per trade
        f_final = min(max(0, f_adj), 0.02)
        risk_usd = acc.equity * f_final
        
        # Calculate lot size based on ATR or SL distance
        # For Sniper, we use a default SL distance if not provided in signal
        # v17.5 directive: Sniper executes but SL/TP are managed remotely
        # However, for MT5 safety, we need some risk metric.
        # We'll use 1% price movement as a proxy for lot calculation if SL is unknown
        sl_dist = info.ask * 0.01 
        
        tick_val = info.trade_tick_value
        tick_size = info.trade_tick_size
        point = info.point
        sl_dist_points = sl_dist / (point + 1e-12)
        point_val = tick_val / (tick_size / point)
        
        raw_vol = risk_usd / (sl_dist_points * point_val + 1e-12)
        
        # Normalize lot size
        lot = round(raw_vol / info.volume_step) * info.volume_step
        return min(max(lot, info.volume_min), info.volume_max)

    def execute_trade(self, symbol, direction, lot, p):
        tick = mt5.symbol_info_tick(symbol)
        if not tick: return
        
        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        price = tick.ask if direction == "BUY" else tick.bid
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot),
            "type": order_type,
            "price": price,
            "magic": MAGIC_NUMBER,
            "comment": f"SENTINEL_v17.5_P{p:.2f}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        res = mt5.order_send(request)
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ [EXECUTED] {symbol} {direction} {lot} lots at {price}")
        else:
            logger.error(f"❌ [FAILED] {symbol} {direction} Error: {res.retcode} - {res.comment}")

    def execute_exit(self, ticket, symbol, reason):
        """Flattens a specific ticket."""
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            logger.warning(f"[{symbol}] Exit failed: Ticket {ticket} not found.")
            return

        pos = positions[0]
        tick = mt5.symbol_info_tick(symbol)
        if not tick: return
        
        order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "magic": MAGIC_NUMBER,
            "comment": f"EXIT_{reason[:15]}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        res = mt5.order_send(request)
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ [EXITED] {symbol} Ticket {ticket} Reason: {reason}")
        else:
            logger.error(f"❌ [EXIT_FAILED] {symbol} Ticket {ticket} Error: {res.retcode}")

if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.message_content = True
    
    sniper = DiscordSniper(intents=intents)
    try:
        sniper.run(BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Shutting down Sniper...")
        mt5.shutdown()
