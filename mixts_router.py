import numpy as np

class HMMOracle:
    def __init__(self):
        self.regimes = ["BULL", "BEAR", "RANGE"]
        self.current_regime = "RANGE"
        self.state_history = []
        self.max_persistence = 50 # Max bars before forced flush

    def get_posterior_probabilities(self, volume_declining=False):
        """v23.2: HMM State Flush Fail-Safe."""
        probs = np.random.dirichlet(np.ones(3), size=1)[0]
        posteriors = dict(zip(self.regimes, probs))
        
        # Detect dominant regime (>90%)
        dominant = max(posteriors, key=posteriors.get)
        if posteriors[dominant] > 0.90:
            self.state_history.append(dominant)
        else:
            self.state_history = []

        # Flush if stuck in Mode Collapse during declining volume
        if len(self.state_history) > self.max_persistence and volume_declining:
            print(f"[HMM] Mode Collapse Detected in {dominant}. Flushing transition matrix...")
            probs = np.array([0.333, 0.333, 0.334]) # Reset to uniform prior
            self.state_history = []
            posteriors = dict(zip(self.regimes, probs))

        return posteriors

class MixTS:
    def __init__(self, oracle):
        self.oracle = oracle
        self.thompson_counts = {"BULL": 1, "BEAR": 1, "RANGE": 1}
        self.thompson_successes = {"BULL": 0, "BEAR": 0, "RANGE": 0}
        self.base_gate = 0.65
    
    def calculate_conviction(self, xgboost_prob, ddqn_prob, faiss_sim=0.0):
        """v23.2: Contextual Hysteresis & FAISS Integration."""
        posteriors = self.oracle.get_posterior_probabilities()
        
        # Directive 2: Dynamic Gate Scaling
        effective_gate = self.base_gate
        if faiss_sim < -0.30:
            effective_gate = max(0.85, effective_gate)
            print(f"[MixTS] FAISS Warning: sim={faiss_sim}. Scaling Gate to {effective_gate}")

        # Thompson Sampling weighting
        weights = {}
        for regime in posteriors:
            weights[regime] = np.random.beta(self.thompson_successes[regime] + 1, 
                                             self.thompson_counts[regime] - self.thompson_successes[regime] + 1)
        
        combined_weights = {r: weights[r] * posteriors[r] for r in weights}
        total_w = sum(combined_weights.values())
        norm_weights = {r: combined_weights[r] / total_w for r in combined_weights}
        
        final_p = (xgboost_prob * norm_weights["BULL"]) + (ddqn_prob * (norm_weights["BEAR"] + norm_weights["RANGE"]))
        
        # Return gate to ensure execution node respects the scaled threshold
        return final_p, norm_weights, effective_gate

if __name__ == "__main__":
    oracle = HMMOracle()
    router = MixTS(oracle)
    p, weights, gate = router.calculate_conviction(0.75, 0.65, faiss_sim=-0.42)
    print(f"MixTS Conviction Score ($P$): {p:.4f} (Gate: {gate})")
    print(f"Regime Weights: {weights}")
