
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
from sentinel_config import WATCHLIST

def get_full_audit():
    print("[SYSTEM] Initializing Full Matrix Audit...")
    
    if not mt5.initialize():
        return "MT5 Initialization Failed."

    # 1. Get Live Positions
    positions = mt5.positions_get()
    pos_data = []
    if positions:
        for p in positions:
            pos_data.append({
                "symbol": p.symbol,
                "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": p.volume,
                "profit": p.profit,
                "magic": p.magic
            })

    # 2. Scan Watchlist for "Close to Firing"
    ac = git_arctic.get_arctic()
    cache = ac['oracle_cache']
    
    close_to_firing = []
    
    for symbol in WATCHLIST:
        try:
            # Check if we already have a position
            if any(p['symbol'] == symbol for p in pos_data):
                continue
                
            m_item = cache.read(f"{symbol}_meta").data.iloc[-1]
            conviction = float(m_item.get('meta_conviction', 0.5))
            direction = int(m_item.get('primary_dir', 0))
            
            # Close to firing if conviction > 0.70 (Gate is 0.82)
            if conviction > 0.70 and direction != 0:
                h_item = cache.read(f"{symbol}_hmm").data.iloc[-1]
                close_to_firing.append({
                    "symbol": symbol,
                    "direction": "BUY" if direction == 1 else "SELL",
                    "conviction": conviction,
                    "hmm_state": h_item.get('state', 'UNKNOWN'),
                    "gap_to_gate": round(0.82 - conviction, 3)
                })
        except:
            continue

    mt5.shutdown()

    # 3. Use Qwen to summarize
    engine = QwenReasoningEngine()
    sys_prompt = "You are the Qwen Reasoning Core. Provide a detailed update on (1) Current Positions and (2) Opportunities Close to Firing. Use markdown tables."
    user_prompt = f"AUDIT DATA:\nPOSITIONS: {json.dumps(pos_data)}\nCLOSE_TO_FIRING: {json.dumps(close_to_firing)}"
    
    try:
        raw_response = engine.generate_with_budget(sys_prompt, user_prompt, budget=600)
        if "<think>" in raw_response:
            return raw_response.split("</think>")[-1].strip()
        return raw_response
    except Exception as e:
        # Fallback to manual summary if Qwen fails
        summary = "### 🧠 Sentinel Matrix Audit (Manual Fallback)\n\n"
        summary += "#### Current Positions\n"
        if pos_data:
            df_pos = pd.DataFrame(pos_data)
            summary += df_pos.to_markdown(index=False) + "\n\n"
        else:
            summary += "No active positions.\n\n"
            
        summary += "#### 🔥 Close to Firing (Conviction > 0.70)\n"
        if close_to_firing:
            df_close = pd.DataFrame(close_to_firing)
            summary += df_close.to_markdown(index=False) + "\n\n"
        else:
            summary += "No assets currently approaching the 0.82 Epistemic Gate.\n"
            
        return summary

if __name__ == "__main__":
    print(get_full_audit())
