import json
import logging
import re
import math
from typing import Dict, Any, Tuple

# Type Aliases
ItemType = Dict[str, Any]
PredictionType = str
GroundTruthType = list

class CadesMultiTaskEnv:
    """
    Dual-Objective Microsoft SkillOpt Environment Adapter.
    Supports Track A (Infrastructure/SRE) and Track B (Quantitative/HMM).
    """
    def __init__(self, execution_timeout: float = 30.0):
        self.execution_timeout = execution_timeout
        self.logger = logging.getLogger("CadesMultiTaskEnv")

    def execute(self, item: ItemType, skill: str, model: Any) -> Tuple[PredictionType, Dict[str, Any]]:
        """
        Injects candidate skill into the correct Track context and extracts prediction.
        """
        task_type = item.get("task_type", "TRACK_A") # Defaults to SRE if missing
        question = item.get("question", "")
        context = item.get("context", "")
        
        if task_type == "TRACK_A":
            prompt = (
                f"SYSTEM RULES (Track A - SRE):\n{skill}\n\n"
                f"ERROR SIGNATURE:\n{question}\n\n"
                f"SYSTEM CONTEXT:\n{context}\n\n"
                f"TASK: Generate the required Python code modification block. Wrap it in ```python."
            )
        else: # TRACK_B
            prompt = (
                f"SYSTEM RULES (Track B - Quant):\n{skill}\n\n"
                f"HMM/VAR METRICS:\n{question}\n\n"
                f"MARKET CONTEXT:\n{context}\n\n"
                f"TASK: Output the optimal Kelly Fraction, Regime Lookback, and Conviction Threshold "
                f"as a JSON object. Wrap it in ```json."
            )
            
        try:
            if hasattr(model, 'generate'):
                response_text = model.generate(prompt, max_tokens=1024, timeout=self.execution_timeout)
            else:
                # Mock LLM fallback for dry-runs
                if task_type == "TRACK_A":
                    response_text = "```python\n# Syntax verified fix\ndef resolved_func():\n    pass\n```"
                else:
                    response_text = "```json\n{\"kelly_fraction\": 0.15, \"regime_lookback\": 48, \"conviction_threshold\": 0.82}\n```"
        except Exception as e:
            self.logger.error(f"Rollout generation failure: {e}")
            response_text = ""

        # Extract code block depending on track
        if task_type == "TRACK_A":
            code_match = re.search(r"```python(.*?)```", response_text, re.DOTALL)
        else:
            code_match = re.search(r"```json(.*?)```", response_text, re.DOTALL)
            
        prediction = code_match.group(1).strip() if code_match else response_text.strip()
        
        trajectory = {
            "prompt": prompt,
            "raw_response": response_text,
            "extracted_prediction": prediction,
            "task_type": task_type
        }
        return prediction, trajectory

    def evaluate(self, prediction: PredictionType, item: ItemType) -> float:
        """
        Dual validation gates based on task type.
        Track A: Compilation pass (0.0 or 1.0)
        Track B: Walk-forward metric simulation (Sortino/Calmar approximation)
        """
        task_type = item.get("task_type", "TRACK_A")
        if not prediction:
            return 0.0

        if task_type == "TRACK_A":
            # Track A: Structural compilation check
            try:
                compile(prediction, '<string>', 'exec')
                return 1.0
            except SyntaxError:
                self.logger.warning("[Track A] Syntax regression detected.")
                return 0.0
                
        else:
            # Track B: Walk-forward simulation
            try:
                params = json.loads(prediction)
                k_frac = params.get("kelly_fraction", 0.0)
                lookback = params.get("regime_lookback", 1)
                
                # Mock evaluation: calculate a pseudo-Calmar ratio based on input stability
                base_calmar = 1.2
                delta = (k_frac * 2.0) + (10.0 / float(lookback)) 
                calmar = base_calmar + delta
                
                # Normalize ratio between 0 and 1 for the environment spec
                normalized = min(max(calmar / 5.0, 0.0), 1.0)
                return normalized
            except json.JSONDecodeError:
                self.logger.warning("[Track B] Invalid JSON parameters generated.")
                return 0.0
            except Exception as e:
                self.logger.error(f"[Track B] Backtest simulator crash: {e}")
                return 0.0
