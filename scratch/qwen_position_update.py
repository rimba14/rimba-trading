
import sys
import os
import json
import time
import MetaTrader5 as mt5
import pandas as pd

# Inject project path
sys.path.append(r"C:\Sentinel_Project")

import git_arctic
from qwen_reasoning_engine import QwenReasoningEngine
import gitagent_utils as utils

def get_live_update():
    print("[SYSTEM] Initializing Qwen Position Audit...")
    
    if not mt5.initialize():
        return "MT5 Initialization Failed. Cannot retrieve positions."

    positions = mt5.positions_get()
    if positions is None or len(positions) == 0:
        mt5.shutdown()
        return "The Sentinel is currently in observation mode. No active positions detected in the matrix."

    # Fetch supplementary data from ArcticDB
    ac = git_arctic.get_arctic()
    cache = ac['oracle_cache']
    
    pos_data = []
    for p in positions:
        symbol = p.symbol
        try:
            h_item = cache.read(f"{symbol}_hmm").data.iloc[-1]
            m_item = cache.read(f"{symbol}_meta").data.iloc[-1]
            
            pos_data.append({
                "symbol": symbol,
                "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": p.volume,
                "profit": p.profit,
                "hmm_state": h_item.get('state', 'UNKNOWN'),
                "conviction": m_item.get('meta_conviction', 0.5)
            })
        except:
            pos_data.append({
                "symbol": symbol,
                "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": p.volume,
                "profit": p.profit,
                "hmm_state": "CACHE_MISS",
                "conviction": 0.5
            })

    mt5.shutdown()

    # Ask Qwen to summarize
    engine = QwenReasoningEngine()
    sys_prompt = "You are the Qwen Reasoning Core for the Adaptive Sentinel trading system. Provide a professional, concise update on current trading positions. Use markdown for the table."
    user_prompt = f"CURRENT POSITIONS DATA: {json.dumps(pos_data)}"
    
    try:
        # Use a slightly larger budget for the summary
        raw_response = engine.generate_with_budget(sys_prompt, user_prompt, budget=500)
        
        # Strip <think> tags for the final user display
        if "<think>" in raw_response:
            parts = raw_response.split("</think>")
            return parts[-1].strip()
        return raw_response
    except Exception as e:
        return f"Error contacting Qwen Core: {e}\n\nRAW DATA: {json.dumps(pos_data, indent=2)}"

if __name__ == "__main__":
    update = get_live_update()
    print("\n" + "="*50)
    print("QWEN POSITION UPDATE:")
    print("="*50)
    print(update)
    print("="*50)
