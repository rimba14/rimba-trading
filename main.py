"""
main.py - MASTER ORCHESTRATOR
Ties all agents together into an autonomous swarm.
Runs on Hyperliquid Testnet per user request.
# TEST EDIT
"""

import os
import time
import schedule
from dotenv import load_dotenv
from eth_account import Account

import nice_funcs_hyperliquid as n
from agents.risk_agent import RiskAgent
from agents.strategy_agent import StrategyAgent
from agents.trading_agent import TradingAgent

# 1. Config & Auth
load_dotenv("C:\\Sentinel_Project\\.env")
ACCOUNT_KEY = os.getenv("HYPER_LIQUID_KEY")
if not ACCOUNT_KEY:
    raise ValueError("HYPER_LIQUID_KEY missing from .env")

account = Account.from_key(ACCOUNT_KEY)
ACCOUNT_ADDRESS = account.address

# Global Parameters
SYMBOL = "BTC"
INTERVAL = "4h"
POSITION_SIZE_USD = 10.0
LEVERAGE = 5
TAKE_PROFIT_PCT = 5.0
STOP_LOSS_PCT = -3.0

# Initialize Agents
risk_agent = RiskAgent(ACCOUNT_ADDRESS)
strategy_agent = StrategyAgent(SYMBOL, INTERVAL)
trading_agent = TradingAgent(SYMBOL, model="qwen")


def bot_cycle():
    """Main execution loop run every 1 minute."""
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
    tech_signal, tech_reason = strategy_agent.run()
    
    if tech_signal in ["BUY", "SELL"]:
        # 2. Risk Check
        allowed, risk_reason = risk_agent.check_trade(SYMBOL, POSITION_SIZE_USD, LEVERAGE)
        if not allowed:
            print(f"[RISK] Blocked: {risk_reason}")
            return
            
        # 3. AI Confirmation (Optional but recommended)
        df = n.get_ohlcv(SYMBOL, INTERVAL, 10)
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
