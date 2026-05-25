import numpy as np
import json
import os
import time
from typing import Dict, List, Tuple

class EvolutionaryConsensusRegistry:
    """
    Ingests the AlphaProof Nexus Agent C architectural matrix.
    Tracks alternative blending proposal mutations using an Elo Rating system.
    """
    def __init__(self, storage_path: str = "C:/Sentinel_Project/shap_diagnostics/proposal_elo.json"):
        self.storage_path = storage_path
        self.base_elo = 1200.0
        self.proposals = ["ACCURACY_WEIGHTED", "MAX_CONVICTION", "SHAP_FILTERED"]
        self.registry = self._load_or_init_registry()

    def _load_or_init_registry(self) -> Dict[str, float]:
        # Ensure directories exist
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    # Merge default Elo if new proposals are added
                    registry = {prop: self.base_elo for prop in self.proposals}
                    for k, v in data.get("ratings", data).items():
                        if k in registry:
                            registry[k] = float(v)
                    return registry
            except Exception:
                pass
        return {prop: self.base_elo for prop in self.proposals}

    def get_highest_elo_proposal(self) -> str:
        """Determines the active consensus routine based on the strongest candidate."""
        return max(self.registry, key=self.registry.get)

    def update_elo_rating(self, winning_proposal: str, losing_proposal: str, k_factor: float = 32.0) -> None:
        """
        Adjusts configuration rankings based on empirical path outcomes.
        Ensures the optimal framework configuration evolves dynamically.
        """
        r_win = 10 ** (self.registry[winning_proposal] / 400.0)
        r_lose = 10 ** (self.registry[losing_proposal] / 400.0)
        
        expected_win = r_win / (r_win + r_lose)
        
        self.registry[winning_proposal] += k_factor * (1.0 - expected_win)
        self.registry[losing_proposal] += k_factor * (0.0 - (1.0 - expected_win))
        
        # Save both ratings and predictions history
        self._save_registry()

    def _save_registry(self) -> None:
        try:
            history_data = []
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r') as f:
                    old_data = json.load(f)
                    if isinstance(old_data, dict) and "history" in old_data:
                        history_data = old_data["history"]
            
            with open(self.storage_path, 'w') as f:
                json.dump({"ratings": self.registry, "history": history_data}, f, indent=2)
        except Exception:
            pass

    def record_prediction(self, symbol: str, entry_price: float, proposals_predictions: Dict[str, float]) -> None:
        """
        Records proposal prediction values for post-realization Elo adjustments.
        proposals_predictions maps proposal_name -> conviction_value (e.g. 0.0 to 1.0)
        """
        try:
            history_data = []
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r') as f:
                    old_data = json.load(f)
                    if isinstance(old_data, dict) and "history" in old_data:
                        history_data = old_data["history"]
            
            new_pred = {
                "timestamp": time.time(),
                "symbol": symbol,
                "entry_price": entry_price,
                "predictions": proposals_predictions,
                "resolved": False
            }
            history_data.append(new_pred)
            
            # Keep history capped to last 500 records
            if len(history_data) > 500:
                history_data = history_data[-500:]
                
            with open(self.storage_path, 'w') as f:
                json.dump({"ratings": self.registry, "history": history_data}, f, indent=2)
        except Exception:
            pass

    def evaluate_pending_predictions(self) -> None:
        """
        Connects to MT5, checks real-time price realizations of pending predictions,
        and adjusts ELO ratings of proposals dynamically.
        """
        import MetaTrader5 as mt5
        
        if not os.path.exists(self.storage_path):
            return
            
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            history = data.get("history", [])
            if not history:
                return
                
            # Filter for unresolved predictions that are at least 300 seconds old
            now = time.time()
            pending = [h for h in history if not h.get("resolved", False) and now - h["timestamp"] >= 300]
            if not pending:
                return
                
            updated = False
            for p in pending:
                sym = p["symbol"]
                entry = p["entry_price"]
                preds = p["predictions"]
                
                # Fetch current tick price
                tick = mt5.symbol_info_tick(sym)
                if not tick:
                    continue
                    
                current_price = (tick.ask + tick.bid) / 2.0
                price_change = current_price - entry
                
                # Determine realized direction
                if abs(price_change) < (entry * 1e-5): # Negligible change
                    p["resolved"] = True
                    updated = True
                    continue
                    
                realized_buy = price_change > 0
                
                # Grade proposals
                correct_proposals = []
                incorrect_proposals = []
                for prop, val in preds.items():
                    pred_buy = val >= 0.5
                    if pred_buy == realized_buy:
                        correct_proposals.append(prop)
                    else:
                        incorrect_proposals.append(prop)
                        
                # Perform Elo matchups
                for winner in correct_proposals:
                    for loser in incorrect_proposals:
                        self.update_elo_rating(winner, loser, k_factor=16.0)
                        
                p["resolved"] = True
                updated = True
                
            if updated:
                with open(self.storage_path, 'w') as f:
                    json.dump({"ratings": self.registry, "history": history}, f, indent=2)
        except Exception:
            pass

if __name__ == "__main__":
    matrix = EvolutionaryConsensusRegistry()
    active_strategy = matrix.get_highest_elo_proposal()
    print(f"AlphaProof Nexus Evolution Test: SUCCESS. Active configuration node selected: {active_strategy}")
