import json
import os
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

AWARENESS_FILE = "C:\\Sentinel_Project\\AWARENESS.md"
REFLECT_LOG = "C:\\Sentinel_Project\\reflection_log.json"

class ReflectiveAgent:
    def __init__(self, palace_db="C:\\Sentinel_Project\\sentinel_palace_graph.json"):
        self.palace_db = palace_db
        self.awareness_limit = 200 # AgentRecall 200-line constraint

    def reflect_on_session(self, current_trades: List[Dict[str, Any]]):
        """Phase 173: Think-Execute-Reflect loop"""
        insights = []
        for trade in current_trades:
            outcome = trade.get('outcome')
            reasoning = trade.get('reasoning', 'STALER_REASONING')
            symbol = trade.get('symbol')
            
            # Logic: If failure but reasoning was high-confidence, it's a 'Reasoning Fault'
            if outcome == "LOSS" and "confidence: HIGH" in reasoning.upper():
                insight = f"REFLECT [{symbol}]: High-confidence trigger failed. Fault: Over-reliance on structural support during news volatility."
                insights.append(insight)
            elif outcome == "WIN" and "regime: 1" in reasoning.upper():
                insight = f"REINFORCE [{symbol}]: Successful Crisis-Mode navigation. Lesson: Sentiment pulse alignment was the key."
                insights.append(insight)

        self._update_awareness(insights)

    def _update_awareness(self, new_insights: List[str]):
        """AgentRecall Compounding Awareness: Constrained to 200 lines for maximum density"""
        existing_lines = []
        if os.path.exists(AWARENESS_FILE):
            with open(AWARENESS_FILE, 'r', encoding='utf-8') as f:
                existing_lines = f.readlines()

        # Phase 173: Compounding logic (Simple append for now, will add LLM-merge later)
        header = f"# 🧠 SENTINEL AWARENESS (Insight Compounding)\n*Last Update: {datetime.now(timezone.utc).isoformat()}*\n\n"
        
        # Keep it tight
        final_content = [header] + new_insights + ["\n"] + existing_lines
        final_content = final_content[:self.awareness_limit]

        with open(AWARENESS_FILE, "w", encoding='utf-8') as f:
            f.writelines([line + "\n" if not line.endswith("\n") else line for line in final_content])

if __name__ == "__main__":
    # Test pass
    mock_trades = [{"symbol": "XAUUSD", "outcome": "LOSS", "reasoning": "Confidence: HIGH | Support at 2300"}]
    reflector = ReflectiveAgent()
    reflector.reflect_on_session(mock_trades)
    print(f"[REFLECTOR] Consciousness updated in {AWARENESS_FILE}.")
