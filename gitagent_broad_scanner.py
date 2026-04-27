import pandas as pd
from gitagent_macro_oracle import MacroOracle
from gitagent_dexter_bridge import DexterBridge
from gitagent_ai4trade_bridge import AI4TradeBridge
from gitagent_sentiment_bridge import get_sentiment_pulse

class OpportunityScanner:
    def __init__(self):
        self.macro = MacroOracle()
        self.dexter = DexterBridge()
        self.ai4trade = AI4TradeBridge()

    def scan_opportunity(self, symbol: str):
        # Technical Pulse (Using neutral mock for broad scan)
        df = pd.DataFrame({'close': [100]*200, 'high': [101]*200, 'low': [99]*200})
        tech_pulse = get_sentiment_pulse(symbol, df)
        
        m_context = self.macro.fetch_polymarket_sentiment(symbol)
        f_health = self.dexter.get_fundamental_health(symbol)
        c_pulse = self.ai4trade.get_consensus_pulse(symbol)
        
        tps = (tech_pulse * 0.4) + (m_context['odds'] * 0.2) + (f_health['health_score']/100.0 * 0.2) + (c_pulse['consensus'] * 0.2)
        
        print(f"[SCAN] {symbol:7} | TPS: {tps:.2f} | T:{tech_pulse:5.2f} M:{m_context['odds']:.2f} F:{f_health['health_score']/100.0:.2f} C:{c_pulse['consensus']:.2f} | Status: {'FIRE' if tps >= 0.6 else 'WAIT'}")

if __name__ == "__main__":
    scanner = OpportunityScanner()
    symbols = ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD", "SP500", "NAS100", "TSLA", "AAPL"]
    print("--- INSTITUTIONAL BROAD WATCHLIST MAP ---")
    for s in symbols:
        scanner.scan_opportunity(s)
