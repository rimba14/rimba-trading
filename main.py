"""
main.py - MASTER ORCHESTRATOR
Ties all agents together into an autonomous swarm.
Runs on Hyperliquid Testnet per user request.
# TEST EDIT
"""

import os
import time
import schedule
import logging
from dotenv import load_dotenv
from eth_account import Account

import nice_funcs_hyperliquid as n
from agents.risk_agent import RiskAgent
from agents.strategy_agent import StrategyAgent
from agents.trading_agent import TradingAgent

# Global Parameters (Default values)
SYMBOL = "BTC"
INTERVAL = "4h"
POSITION_SIZE_USD = 10.0
LEVERAGE = 5
TAKE_PROFIT_PCT = 5.0
STOP_LOSS_PCT = -3.0

# Global Agents & Account (Initialized in initialize())
risk_agent = None
strategy_agent = None
trading_agent = None
account = None
ACCOUNT_ADDRESS = None

def initialize():
    """Initializes authentication and agents."""
    global risk_agent, strategy_agent, trading_agent, account, ACCOUNT_ADDRESS

    load_dotenv("C:\\Sentinel_Project\\.env")
    ACCOUNT_KEY = os.getenv("HYPER_LIQUID_KEY")
    if not ACCOUNT_KEY:
        # For testing purposes, we might want a fallback or to handle this gracefully
        # but the original code raised ValueError.
        # When importing for tests, we can mock initialize or set the env var.
        raise ValueError("HYPER_LIQUID_KEY missing from .env")

    account = Account.from_key(ACCOUNT_KEY)
    ACCOUNT_ADDRESS = account.address

    # Initialize Agents
    risk_agent = RiskAgent(ACCOUNT_ADDRESS)
    strategy_agent = StrategyAgent(SYMBOL, INTERVAL)
    trading_agent = TradingAgent(SYMBOL, model="qwen")
    print(f"Agents initialized for account: {ACCOUNT_ADDRESS}")

def bot_cycle():
    """Main execution loop run every 1 minute."""
    if any(a is None for a in [risk_agent, strategy_agent, trading_agent, account]):
        print("[ERROR] Agents not initialized. Call initialize() first.")
        return

    print("\n" + "="*50)
    print(f"[{time.strftime('%H:%M:%S')}] New Bot Cycle Started")
    print("="*50)
    
    # A. Active Position Management
    pos = n.get_position(SYMBOL, ACCOUNT_ADDRESS)
    if pos["in_pos"]:
        print(f"[POS] In {SYMBOL} {'LONG' if pos['long'] else 'SHORT'}. PnL: {pos['pnl_pct']:.2f}%")
        n.pnl_close(SYMBOL, TAKE_PROFIT_PCT, STOP_LOSS_PCT, account)
        return # Skip entry logic if in position

    # B. Look for New Entry
    n.cancel_all_orders(account)
    
    # 1. Strategy Signal
    # Note: strategy_agent.run() in strategy_agent.py expects ohlcv_dict.
    # In the original main.py it was called without args.
    # Checking original main.py: tech_signal, tech_reason = strategy_agent.run()
    # Checking strategy_agent.py: def run(self, ohlcv_dict: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    # It seems it was returning HOLD if ohlcv_dict is None.
    # Wait, the original main.py MUST have worked somehow.
    # Ah, maybe strategy_agent.run() was different?
    # Let's re-read strategy_agent.run in main.py's context.

    # Actually, I should probably fetch data here if it's missing.
    df = n.get_ohlcv(SYMBOL, INTERVAL, 10)
    ohlcv_dict = {"close": df["close"].tolist()} if not df.empty else None
    tech_signal, tech_reason = strategy_agent.run(ohlcv_dict)
    
    if tech_signal in ["BUY", "SELL"]:
        # 2. Risk Check
        allowed, risk_reason = risk_agent.check_trade(SYMBOL, POSITION_SIZE_USD, LEVERAGE)
        if not allowed:
            print(f"[RISK] Blocked: {risk_reason}")
            return
            
        # 3. AI Confirmation (Optional but recommended)
        ai_res = trading_agent.analyze(df, tech_signal, tech_reason)
        print(f"[AI] Decision: {ai_res['decision']} (Confidence: {ai_res['confidence']})")
        print(f"[AI] Reasoning: {ai_res['reasoning']}")
        
        if ai_res["decision"] == tech_signal:
            print(f"*** [EXECUTE] Signals Aligned! Firing {tech_signal} order. ***")
            ask, bid = n.ask_bid(SYMBOL)
            _, size = n.adjust_leverage_usd_size(SYMBOL, POSITION_SIZE_USD, LEVERAGE, account)
            
            is_buy = (tech_signal == "BUY")
            limit_px = bid if is_buy else ask
            
            res = n.limit_order(SYMBOL, is_buy, size, limit_px, False, account)
            print(f"[ORDER] Result: {res}")
        else:
            print("[AI] Filtered out technical signal. Staying neutral.")

def run_bot():
    """Entry point."""
    print(f"Moon Dev Framework Initiated on Testnet!")

    if ACCOUNT_ADDRESS is None:
        initialize()

    print(f"Account: {ACCOUNT_ADDRESS}")
    print(f"Symbol: {SYMBOL} | Size: ${POSITION_SIZE_USD} | Setup complete.")
    
    # Run immediate first cycle
    bot_cycle()
    
    # Schedule every 1 minute (or interval matching candles)
    schedule.every(1).minutes.do(bot_cycle)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    run_bot()
