import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import os
import time
import json
from gitagent_base import BaseModule
from typing import Dict, Any, List
# ...
from gitagent_memory_fast import FastMemory
from gitagent_groq_lpu import GroqReasoningEngine

class ContextLayer(BaseModule):
    """
    Sentinel Context Layer (Layer 4)
    Responsibility: Hermes Vector Retrieval -> LLM Reasoning -> Context Injection.
    Input: Cognition Result (Layer 3)
    Output: Context-Aware Directive
    """
    def __init__(self):
        super().__init__("Context")
        self.memory = FastMemory(dim=89)
        self.groq = GroqReasoningEngine(model_name="llama-3.1-8b-instant")

    def process(self, cognition_data: Dict[str, Any]) -> Dict[str, Any]:
        verdict = cognition_data.get('verdict', 'HOLD')
        
        # 1. Hermes Memory Retrieval
        context_vector = np.zeros(89).astype('float32')
        history = self.memory.retrieve(context_vector, k=1)
        
        # 2. Inconsistency Monitor
        inconsistent = False
        if "LOSS" in str(history).upper() and verdict == "BUY":
            inconsistent = True
            print("[MONITOR] Inconsistency detected: Past BUYs in this regime led to LOSS.")

        # 3. Context Injection (Cognition Bridge)
        cognition_factor = 0.0
        try:
            with open("C:\\Sentinel_Project\\cognition_bridge.json", "r") as f:
                cdata = json.load(f)
                cognition_factor = cdata.get('cognition_factor', 0.0)
        except:
            pass

        aware_verdict = verdict
        if cognition_factor < -0.4 and verdict != "SELL":
            aware_verdict = "HOLD" 
        
        return {
            "final_verdict": aware_verdict,
            "is_inconsistent": inconsistent,
            "cognition_factor": cognition_factor,
            "history_summary": str(history)[:100],
            "timestamp": time.time()
        }

def run_forensic_audit():
    """Background audit loop (non-linear path)."""
    pass
