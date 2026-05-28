import os
import requests
import json
from typing import Dict, Any, List
import typing
from gitagent_base import BaseModule
from gitagent_gemma_connector import GemmaContextLayer
from gitagent_kronos_adapter import get_kronos_forecast
from gitagent_vision_audit import VisionPatternAgent

try:
    import google.genai  # noqa: F401
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    import groq  # noqa: F401
    HAS_GROQ_SDK = True
except ImportError:
    HAS_GROQ_SDK = False

class UniversalContextLayer(BaseModule):
    """
    Sentinel Context Layer (Layer 4) - Unified Switchboard
    Responsibility: Autonomous Routing & Forensic Audit.
    Backends: Local (Ollama), Performance (Groq), Cognitive (Gemini).
    """
    def __init__(self):
        super().__init__("Context")
        self.gemma_cloud = GemmaContextLayer()
        self.vision_agent = VisionPatternAgent()
        
    def process(self, cognition_receipt: Dict[str, Any]) -> Dict[str, Any]:
        """Phase 225: Dual-Oracle Audit (Vision + Kronos + Episodic Memory)."""
        action = cognition_receipt.get('action') or cognition_receipt.get('verdict') or 'NONE'
        sym = cognition_receipt.get('symbol', '?')
        df = cognition_receipt.get('ohlcv_df')
        tensor = cognition_receipt.get('feature_tensor')
        
        # ─── Phase 165: Contextual Query Override (Legendary Match) ───
        legendary_boost = False
        if tensor is not None:
            try:
                from gitagent_memory import EpisodicMemory
                memory = EpisodicMemory(dim=93)
                # k=1 for highest fidelity match
                matches = memory.retrieve(tensor, k=1)
                if matches:
                    m = matches[0]
                    # Threshold: 0.15 distance is ~85% similarity in FlatL2 space
                    if m['distance'] < 0.15 and m['meta'].get('lesson') == 'legend_wei':
                        print(f"[CONTEXT] 🏛️ LEGENDARY MATCH: {sym} matches institutional template (Dist: {m['distance']:.3f}).")
                        legendary_boost = True
            except Exception as e:
                print(f"[CONTEXT_ERR] Memory lookup failed: {e}")

        if action in ["BUY", "SELL"] and df is not None:
            print(f"[CONTEXT] {sym} | High Conviction {action} detected. Initiating Dual-Oracle...")
            
            # 1. Numerical Oracle: Kronos
            kronos_res = get_kronos_forecast(df)
            k_bias = kronos_res.get('bias', 0.0)
            
            # 2. Visual Oracle: Vision Audit
            vision_res = self.vision_agent.audit_visual_structure(df, sym, action)
            v_verdict = vision_res.get('vision_verdict', 'NEUTRAL')
            v_conf = vision_res.get('vision_confidence', 0.5)
            
            # 3. Agentic Multi-Hypothesis Debate
            final_action, final_reasoning = self._hypothesis_debate(sym, action, k_bias, vision_res)
            
            # If Vision says REJECTED, we normally downgrade to HOLD
            # UNLESS we have a Legendary Match (Phase 165 Override)
            if v_verdict == "REJECTED" and v_conf > 0.7:
                if legendary_boost:
                    print(f"[CONTEXT] 🛡️ OVERRIDING VISION REJECTION: Legendary template detected for {sym}.")
                    final_reasoning = f"LEGEND_OVERRIDE: {final_reasoning}"
                else:
                    return "HOLD", f"VISION_REJECTION: {vision_res.get('vision_rationale')}", "VISION-ORACLE"
            
            # Boost directional confidence if legendary
            if legendary_boost:
                final_reasoning = f"LEGENDARY_CONFIRMATION | {final_reasoning}"
            
            return final_action, final_reasoning, "TRIPLE-ORACLE-SYSTEM"

        return "HOLD", "NO_CONVICTION", "HAPPO-STRUCTURAL"

    def _hypothesis_debate(self, symbol: str, signal: str, k_bias: float, vision_res: dict) -> typing.Tuple[str, str]:
        """
        Synthesizes multiple hypotheses into a final verdict.
        Compares Trend Continuation vs. Mean Reversion.
        """
        # We use the existing Gemma cloud for the logic-heavy debate
        v_rationale = vision_res.get('vision_rationale', 'No vision data.')
        
        prompt = f"""
        AGENTIC MULTI-HYPOTHESIS DEBATE: {symbol}
        Proposed Signal: {signal}
        Numerical Oracle (Kronos Bias): {k_bias:+.2f}
        Vision Oracle: {vision_res.get('vision_verdict')} ({vision_res.get('vision_confidence'):.2f} conf)
        Vision Details: {v_rationale}
        
        DEBATE HYPOTHESES:
        A (Trend): This is a valid momentum continuation. High volatility supports the expansion.
        B (Contrarian): This is an exhausted move hitting a structural ceiling. Reversal is imminent.
        
        TASK: Weigh Hypotheses A & B. Decide if we EXECUTE or ABORT.
        If Kronos and Vision are in conflict, default to ABORT.
        
        RESPONSE FORMAT: [DECISION] | [LOGIC]
        DECISION: EXECUTE or ABORT.
        """
        
        # Using Gemini-2.0-Flash-Lite as defined in the class for high-reasoning debate
        res_text, _ = self._gemini_inference({"symbol": symbol, "prompt_override": prompt})
        
        # For efficiency, we use the local or cloud prompt
        if "EXECUTE" in res_text.upper():
            return signal, f"Hypothesis A Won: {res_text[:150]}"
        return "HOLD", f"Hypothesis B Won (Abort): {res_text[:150]}"

    def process_batch(self, cognition_receipts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Phase 41 FIX: Forward batch request to Gemma 3 Cloud bridge."""
        if self.gemma_cloud is None:
            print("[CONTEXT] Warning: gemma_cloud is None. Falling back to individual processing.")
            return [self.process(r) for r in cognition_receipts]
        return self.gemma_cloud.process_batch(cognition_receipts)

    def _local_inference(self, data: Dict) -> typing.Tuple[str, str]:
        payload = {
            "model": "gemma:2b",
            "messages": [{"role": "user", "content": self._build_prompt(data)}],
            "stream": False
        }
        try:
            r = requests.post(self.local_url, json=payload, timeout=30)
            return r.json().get('message', {}).get('content', ''), "LOCAL-OLLAMA"
        except Exception as e:
            return f"LOCAL ERROR: {str(e)}", "LOCAL-FAIL"

    def _groq_inference(self, data: Dict) -> typing.Tuple[str, str]:
        try:
            if self.groq_client:
                chat = self.groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": self._build_prompt(data)}],
                    max_tokens=128
                )
                return chat.choices[0].message.content, "GROQ-PERFORMANCE"
            # Fallback to requests if SDK not available
            headers = {"Authorization": f"Bearer {self.groq_key}"}
            payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": self._build_prompt(data)}]}
            r = requests.post(self.groq_url, headers=headers, json=payload, timeout=5)
            return r.json().get('choices', [{}])[0].get('message', {}).get('content', ''), "GROQ-PERFORMANCE"
        except Exception as e:
            return f"GROQ ERROR: {str(e)}", "GROQ-FAIL"

    def _gemini_inference(self, data: Dict) -> typing.Tuple[str, str]:
        prompt = data.get("prompt_override") or self._build_prompt(data)
        try:
            # Simple REST fallback if genai client not ready
            headers = {"Content-Type": "application/json"}
            api_key = os.environ.get("GOOGLE_API_KEY")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={api_key}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            data = r.json()
            return data['candidates'][0]['content']['parts'][0]['text'], "GEMINI-COGNITION"
        except Exception as e:
            return f"GEMINI ERROR: {str(e)}", "GEMINI-FAIL"

    def _build_prompt(self, data: Dict) -> str:
        module_10 = data.get('module_10', {})
        m10_score = data.get('m10_score', 0.0)
        
        return f"""
        FINANCIAL FORENSIC AUDIT: {data.get('symbol', 'UNKNOWN')}
        Regime: {data.get('regime')}
        Confidence: {data.get('confidence')}
        Cognition Factor: {data.get('cognition_factor')}
        
        STRUCTURAL EVIDENCE (Module 10):
        - Current Flip Score: {m10_score} / 8.0
        - Details: {json.dumps(module_10)}
        
        DIRECTIVE:
        Combine the structural evidence from our Module 10 codebase logic with your high-level market reasoning.
        If the structural evidence is weak but your reasoning is strongly bearish, you may recommend SELL.
        
        VERDICT MUST BE: BUY, SELL, or HOLD.
        PROVIDE 1 SENTENCE REASONING.
        """
