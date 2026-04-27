import MetaTrader5 as mt5
import pandas as pd
import json
import os
from datetime import datetime, timezone
from gitagent_gemma_connector import GemmaContextLayer

class ForensicEngine:
    """
    Sentinel Forensic Layer (Layer 5)
    Responsibility: Post-mortem analysis of closed deals using Gemma-4.
    Feeds back into the RSI (Recursive Self-Improvement) dataset.
    """
    def __init__(self):
        self.gemma = GemmaContextLayer()
        self.log_file = "C:\\Sentinel_Project\\sentinel_forensics.json"

    def audit_deal(self, deal, entry_snapshot):
        """Perform a deep forensic audit of a single closed deal."""
        sym = deal.symbol
        pnl = deal.profit
        
        # 1. Gather Exit Context (OHLCV)
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 20)
        if rates is None: return "Insufficient exit data"
        
        df_exit = pd.DataFrame(rates)
        
        # 2. Construct Forensic Prompt
        prompt = f"""
        FINANCIAL POST-MORTEM: {sym}
        Trade ID: {deal.position_id}
        PnL: ${pnl:.2f} ({'PROFIT' if pnl > 0 else 'LOSS'})
        Entry Mode: {entry_snapshot.get('trend', 'Unknown')}
        Entry Score: {entry_snapshot.get('entry_score', 0.0):.2f}
        
        DE-BRIEF OBJECTIVE: 
        Analyze why this trade resulted in a { 'success' if pnl > 0 else 'failure' }. 
        Consider the OHLCV behavior at exit. 
        Identify if this was a 'Good Win', 'Bad Win', 'Good Loss', or 'Bad Loss' (e.g. following rules vs emotional error).
        
        Provide a 2-sentence forensic critique.
        """
        
        # 3. Call Gemma-4
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 250
            }
        }
        
        # Direct REST call via connector's credentials
        import requests
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(self.gemma.api_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            critique = data['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception as e:
            critique = f"Forensic failure: {e}"
            
        # 4. Archive results
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trade_id": deal.position_id,
            "symbol": sym,
            "pnl": pnl,
            "critique": critique
        }
        self._archive(entry)
        
        print(f"[FORENSIC] {sym} Critique: {critique}")
        return critique

    def _archive(self, entry):
        data = []
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r') as f:
                    data = json.load(f)
            except: pass
        data.append(entry)
        with open(self.log_file, 'w') as f:
            json.dump(data[-500:], f, indent=2) # Keep last 500

if __name__ == "__main__":
    if mt5.initialize():
        # Test logic (latest deal)
        import datetime
        from_date = datetime.datetime.now() - datetime.timedelta(days=1)
        deals = mt5.history_deals_get(from_date, datetime.datetime.now())
        if deals:
            fe = ForensicEngine()
            # In a real run, we'd pass the actual thesis snapshot
            fe.audit_deal(deals[-1], {"entry_score": 0.0})
        mt5.shutdown()
