import sys
import os
import MetaTrader5 as mt5

# Add project root to path
sys.path.append("C:/Sentinel_Project")

print("=== STEP 1: Initializing MT5 ===")
if not mt5.initialize():
    print("MT5 Init failed. Aborting.")
    exit(1)
print("MT5 initialized successfully.")

print("\n=== STEP 2: Running exposure calculation on live inventory ===")
import agents.risk_agent as ra

positions = mt5.positions_get()
if positions:
    print(f"Total live positions retrieved: {len(positions)}")
    for p in positions:
        base, quote = ra.parse_base_quote(p.symbol)
        print(f"  Position: symbol={p.symbol} (base={base}, quote={quote}), volume={p.volume}, price_open={p.price_open}, sl={p.sl}, type={p.type}")
else:
    print("No active open positions in MT5. We will mock a position set to test the mathematical aggregator!")
    
    # Create mock positions representing:
    # 1. Buy EURUSD 0.05 lots at 1.0850, SL at 1.0750 (Risk = 50 USD if contract size = 10,000)
    # 2. Buy GBPUSD 0.05 lots at 1.2500, SL at 1.2400 (Risk = 50 USD)
    # Total long USD risk is negative (selling quote USD): EURUSD quote is USD (-50), GBPUSD quote is USD (-50) -> net short USD -100 USD.
    # Total long EUR risk (+50 USD), long GBP risk (+50 USD).
    class MockPosition:
        def __init__(self, symbol, type, volume, price_open, sl):
            self.symbol = symbol
            self.type = type
            self.volume = volume
            self.price_open = price_open
            self.sl = sl

    positions = [
        MockPosition("EURUSD", 0, 0.05, 1.0850, 1.0750),
        MockPosition("GBPUSD", 0, 0.05, 1.2500, 1.2400)
    ]
    print("Using 2 mock positions for simulation:")
    print("  1. BUY EURUSD 0.05 lots, SL 1.0750 (50 USD Risk)")
    print("  2. BUY GBPUSD 0.05 lots, SL 1.2400 (50 USD Risk)")

# Run exposures calculation
exposures = ra.calculate_currency_exposure(positions)
print("\nActive currency exposures (USD):")
for cur, exp_usd in exposures.items():
    print(f"  {cur}: ${exp_usd:.2f}")

print("\n=== STEP 3: Simulating 4% Correlation Cap Veto ===")
agent = ra.RiskAgent()

# Let's say account equity is $1000. 4% heat cap is $40 limit.
# Mock account info returning $1000 equity
class MockAccountInfo:
    def __init__(self, equity):
        self.equity = equity

original_account_info = mt5.account_info
# Monkeypatch account_info to return mock $1000 equity
mt5.account_info = lambda: MockAccountInfo(1000.0)

# A new BUY EURUSD signal arrives with notional size $5000 (which represents $100 USD risk at 2% ATR fallback)
# Adding $100 EUR risk (total $150 EUR, which is 15.0% of equity) -> should trigger heat limit veto (limit is $40)
print("Simulating incoming trade check:")
print("  Incoming trade: BUY EURUSD, Size: $2000 (Notional)")
allow, reason = agent.check_trade("EURUSD", 2000.0, 10.0, xgb_p=0.85, ddqn_p=0.80)
print(f"  Trade Allowed: {allow}")
print(f"  Veto Reason: {reason}")

# Clean up monkeypatch
mt5.account_info = original_account_info
mt5.shutdown()
print("\n=== PORTFOLIO HEAT VALIDATION COMPLETE ===")
