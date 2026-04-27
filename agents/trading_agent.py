"""
trading_agent.py - AI DECISION MAKER
Uses LLMs to analyze market data and confirm technical signals.
"""

import nice_funcs_hyperliquid as n
from model_factory import ModelFactory
import json

class TradingAgent:
    def __init__(self, symbol, model="qwen"):
        self.symbol = symbol
        self.model = model

    def analyze(self, df, tech_signal, tech_reason):
        """
        Uses LLM to audit a technical signal.
        """
        # Format the latest data for the LLM
        latest_data = df.tail(5).to_json()
        
        system_prompt = f"""
        You are Moon Dev's Master Trading Agent. 
        Your goal is to audit technical signals and ensure we only trade high-probability setups.
        Technical Signal: {tech_signal} ({tech_reason})
        Symbol: {self.symbol}
        """
        
        user_prompt = f"""
        Analyze the following recent candle data and the technical signal provided.
        Recent Data:
        {latest_data}
        
        Should we follow this signal? 
        Respond in JSON format:
        {{
            "decision": "BUY" | "SELL" | "HOLD",
            "confidence": 0.0-1.0,
            "reasoning": "Brief explanation"
        }}
        """
        
        response = ModelFactory.call(self.model, system_prompt, user_prompt)
        
        try:
            # Clean up response if LLM adds markdown
            clean_res = response.strip()
            if "```json" in clean_res:
                clean_res = clean_res.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_res:
                clean_res = clean_res.split("```")[1].split("```")[0].strip()
            
            return json.loads(clean_res)
        except Exception as e:
            print(f"[TRADING_AGENT] Error parsing LLM response: {e}")
            return {"decision": "HOLD", "confidence": 0.0, "reasoning": "LLM Error"}

if __name__ == "__main__":
    # Test
    pass
