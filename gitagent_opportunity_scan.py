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
        # 1. Technical Pulse
        df = pd.DataFrame({'close': [100]*200, 'high': [101]*200, 'low': [99]*200})
        tech_pulse = get_sentiment_pulse(symbol, df)
        
        # 2. Institutional Barriers
        m_context = self.macro.fetch_polymarket_sentiment(symbol)
        f_health = self.dexter.get_fundamental_health(symbol)
        c_pulse = self.ai4trade.get_consensus_pulse(symbol)
        
        # Scoring logic (TPS emulation)
        tps = (tech_pulse * 0.4) + (m_context['odds'] * 0.2) + (f_health['health_score']/100.0 * 0.2) + (c_pulse['consensus'] * 0.2)
        
        print(f"\n[SCAN] {symbol} | TPS: {tps:.2f}")
        print(f" -> Tech: {tech_pulse:.2f} | Macro: {m_context['odds']:.2f} | Fund: {f_health['health_score']/100.0:.2f} | Coll: {c_pulse['consensus']:.2f}")
        
        if tps < 0.6:
            reason = "REJECTED: Signal is 'Muddled' across intelligence layers."
            if tech_pulse > 0.5: reason = "REJECTED: Technical signal exists but lacks Macro/Fund confirmation."
            print(f" -> {reason}")
        else:
            print(" -> ALIGNED: High-Conviction Opportunity Detected.")

if __name__ == "__main__":
    scanner = OpportunityScanner()
    symbols = ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD", "SP500", "NAS100", "TSLA", "AAPL"]
    print("--- INSTITUTIONAL BROAD WATCHLIST SCAN ---")
    for s in symbols:
        scanner.scan_opportunity(s)
