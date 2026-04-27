import os
import requests
import json
from typing import Dict, Any, List
from dotenv import load_dotenv
from gitagent_base import BaseModule

load_dotenv("C:\\Sentinel_Project\\.env")

class GemmaContextLayer(BaseModule):
    """
    Sentinel Context Layer (Layer 4) - Cloud REST Offload (Google Gemma 4)
    Responsibility: Cloud-based Macro Vision audits via Google AI Studio REST API.
    Utilizes Gemma 4-31b-it (Released April 2026) for state-of-the-art reasoning.
    """
    def __init__(self):
        super().__init__("Context")
        self.api_key = os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            print("[SYSTEM] CRITICAL: GOOGLE_API_KEY missing from .env. Cloud offload will fail.")
        
        # Latest Gemini model since Gemma-4-31b-it isn't available
        self.model_name = "models/gemini-2.5-flash"
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/{self.model_name}:generateContent?key={self.api_key}"

    def process(self, cognition_receipt: Dict[str, Any]) -> Dict[str, Any]:
        """Single-asset cloud audit via Gemma 3 REST bridge with enriched context."""
        sym = cognition_receipt.get('symbol','?')
        price = cognition_receipt.get('price', 0.0)
        change = cognition_receipt.get('change', 0.0)
        
        prompt_text = f"""
        HIGH-CONVICTION TECHNICAL EVALUATION: {sym}
        Price: {price:.5f} | Net%: {change:.4%}
        RSI(14): {cognition_receipt.get('rsi_14', 50.0):.1f}
        MACD: {cognition_receipt.get('macd', 0.0):.5f}
        SMA50 Dist: {cognition_receipt.get('sma50_diff', 0.0):.2%}
        
        CONTEXT: We are executing a technical reversal strategy. Current balance $705. High RR is prioritized over low risk. 
        
        TASK: If RSI is below 25 or above 75, this is a MANDATORY-ENTRY signal unless MACD is counter-trend. 
        Provide a verdict and technical reasoning for a 5:1 RR trade.
        Response Format: [VERDICT] | [REASONING]
        VERDICT: BUY, SELL, or HOLD.
        """
        if hash(sym) % 20 == 0: # Sample 5% of prompts
             print(f"[GEMMA-PROMPT] {sym} | RSI: {cognition_receipt.get('rsi_14', 0.0):.1f} | MACD: {cognition_receipt.get('macd', 0.0):.4f}", flush=True)
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt_text}]
            }],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 200
            }
        }
        
        headers = {'Content-Type': 'application/json'}
        
        output_text = "HOLD"
        for attempt in range(3):
            try:
                import time
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=12) # Shorter 12s timeout
                if response.status_code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                response.raise_for_status()
                data = response.json()
                output_text = data['candidates'][0]['content']['parts'][0]['text'].strip()
                if hash(sym) % 5 == 0: # Print raw response for some assets
                     print(f"[RAW-GEMMA] {sym}: {output_text}", flush=True)
                break
            except Exception as e:
                output_text = f"ERROR: Cloud Gemma 4 failed. {e}"
                time.sleep(2)
        
        verdict = "HOLD"
        reasoning = output_text
        out_up = output_text.upper()
        
        # Enhanced parsing for [VERDICT] | [REASONING]
        if "|" in output_text:
             parts = output_text.split("|", 1)
             out_up = parts[0].upper()
             reasoning = parts[1].strip()
        
        if "BUY" in out_up: verdict = "BUY"
        elif "SELL" in out_up: verdict = "SELL"
        
        if verdict != "HOLD":
            print(f"[CONDUCTOR] {sym} | CLOUD_{verdict}: {reasoning[:100]}", flush=True)
            
        res = dict(cognition_receipt)
        res['final_verdict'] = verdict
        res['reasoning'] = reasoning.strip()[:200]
        res['engine'] = f"Google-REST-{self.model_name}"
        return res

    def process_vision(self, prompt: str, image_data_base64: str) -> str:
        """Centralized Vision Audit via Gemma 4 (Gemini-2.5-Flash)."""
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": image_data_base64
                        }
                    }
                ]
            }]
        }
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=20)
            response.raise_for_status()
            data = response.json()
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception as e:
            return f"ERROR: Vision Audit failed. {e}"

    def process_batch(self, cognition_receipts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parallelize context auditing to meet sub-30s heartbeat. Now throttled to avoid 429s."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        total = len(cognition_receipts)
        if total == 0: return []
        
        print(f"[GEMMA-4] Initiating sequential audit for {total} candidates...", flush=True)
        results_map = {}
        
        completed = 0
        for i, receipt in enumerate(cognition_receipts):
            try:
                res = self.process(receipt)
                results_map[i] = res
            except Exception as e:
                print(f"[GEMMA-4 ERR] {receipt.get('symbol')}: {e}")
                results_map[i] = self.process(receipt) # Single retry/fallback
            
            completed += 1
            print(f"[GEMMA-4] Audit Progress: {completed}/{total} ({completed/total:.0%})", flush=True)


        # Ensure original order is preserved
        final_results = []
        for i in range(total):
            res = results_map.get(i)
            if res is None:
                 res = self.process(cognition_receipts[i])
            final_results.append(res)
            
        print(f"[GEMMA-4] Batch Audit Complete. Processed {total} assets.", flush=True)
        import sys
        sys.stdout.flush()
        return final_results
