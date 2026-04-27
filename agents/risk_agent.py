"""
risk_agent.py - PORTFOLIO GUARDIAN
The sovereign risk-management layer. Overrides all other agents.
"""

import os
import json
import time
import nice_funcs_hyperliquid as n

class RiskAgent:
    def __init__(self, account_address):
        self.address = account_address
        
        # Risk Parameters
        self.max_position_size_usd = 50.0   # Cap for Testnet
        self.max_leverage          = 5      # 5x Isolated max
        self.daily_drawdown_limit  = 0.05   # 5% Max daily loss
        self.total_portfolio_limit = 500.0  # Max total exposure
        
        # State tracking
        self.high_water_mark = 0.0
        self.circuit_breaker_active = False

    def check_trade(self, symbol, size_usd, leverage):
        """
        Final check before any order is allowed.
        Returns (allow: bool, reason: str)
        """
        # 1. Check Circuit Breaker
        if self.circuit_breaker_active:
            return False, "Circuit breaker active. Daily drawdown limit hit."

        # 2. Check Leverage
        if leverage > self.max_leverage:
            return False, f"Leverage {leverage}x exceeds max allowed {self.max_leverage}x."

        # 3. Check Position Size
        if size_usd > self.max_position_size_usd:
            return False, f"Position size ${size_usd} exceeds cap ${self.max_position_size_usd}."

        # 4. Check Existing Exposure
        # Simplified: check all HL positions (would normally sum across all coins)
        pos = n.get_position(symbol, self.address)
        if pos["in_pos"]:
            return False, f"Already in a position for {symbol}. No doubling down."

        return True, "Risk check passed."

    def monitor_portfolio(self):
        """
        Runs independently to check for emergency exits.
        In a full swarm, this would run in a separate thread.
        """
        # Placeholder for real portfolio monitor logic
        # Would fetch account equity, compare to high-water mark, etc.
        pass

if __name__ == "__main__":
    # Test
    ra = RiskAgent("0x0000000000000000000000000000000000000000")
    print(ra.check_trade("BTC", 10.0, 5))
