import pandas as pd
import time
from gitagent_macro_oracle import MacroOracle
from gitagent_dexter_bridge import DexterBridge
from gitagent_ai4trade_bridge import AI4TradeBridge
from gitagent_sentiment_bridge import get_sentiment_pulse

class MondayAuditor:
    def __init__(self):
        self.macro = MacroOracle()
        self.dexter = DexterBridge()
        self.ai4trade = AI4TradeBridge()

    def audit_position(self, symbol: str, entry_price: float, side: str):
        print(f"\n[AUDIT] {symbol} {side} @ {entry_price}")
        
        # 1. Macro Context (last30days/Polymarket)
        m_context = self.macro.fetch_polymarket_sentiment(symbol)
        print(f" -> Macro: {m_context['summary']} (Odds: {m_context['odds']})")
        
        # 2. Fundamental Health (Dexter)
        f_health = self.dexter.get_fundamental_health(symbol)
        print(f" -> Fundamental: {f_health['verdict']} (Score: {f_health['health_score']})")
        
        # 3. Collective Intelligence (AI4Trade)
        c_pulse = self.ai4trade.get_consensus_pulse(symbol)
        print(f" -> Collective: {c_pulse['sentiment']} (Consensus: {c_pulse['consensus']})")
        
        # Alignment Score (0 to 100)
        score = (m_context['social_score'] * 33) + (f_health['health_score'] * 0.33) + (c_pulse['consensus'] * 34)
        print(f" -> FINAL ALIGNMENT SCORE: {score:.1f}/100")
        
        if score < 40:
            print(" [!] ACTION: REJECTED - Immediate Exit Recommended.")
        elif score < 60:
            print(" [!] ACTION: WEAK - Reduce Exposure.")
        else:
            print(" [!] ACTION: MAINTAIN - Institutional Alignment Confirmed.")

if __name__ == "__main__":
    auditor = MondayAuditor()
    positions = [
        ("SOLUSD", 82.53, "BUY"),
        ("SP500", 6827.1, "SELL"),
        ("EURGBP", 0.87118, "BUY"),
        ("GBPUSD", 1.34502, "BUY"),
        ("XAGUSD", 75.961, "BUY")
    ]
    for sym, price, side in positions:
        auditor.audit_position(sym, price, side)
