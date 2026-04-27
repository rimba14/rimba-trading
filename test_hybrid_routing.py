import os
import sys
# Mock the necessary components for testing
sys.path.append('C:\\Sentinel_Project\\')
from gitagent_context_layer import UniversalContextLayer

def test_routing():
    layer = UniversalContextLayer()
    
    scenarios = [
        {"name": "NORMAL_STABLE", "data": {"regime": "STABLE", "confidence": 0.5, "urgency": "LOW", "cognition_factor": 4.0}},
        {"name": "HIGH_CONVICTION_ENTRY", "data": {"regime": "TREND", "confidence": 0.9, "urgency": "MEDIUM", "cognition_factor": 8.7}},
        {"name": "EXTREME_VOL_CRASH", "data": {"regime": "EXTREME_VOLATILITY", "confidence": 0.6, "urgency": "HIGH", "cognition_factor": 5.5}},
    ]
    
    print("--- HYBRID ROUTING VERIFICATION ---")
    for s in scenarios:
        print(f"\nScenario: {s['name']}")
        # We catch exceptions because APIs might not be reachable in this environment
        # but we want to see which engine it TRIES to use.
        # We can look at the engine routing logic specifically.
        
        # Test routing decision by mocking the inference calls if needed
        # Or just run and see engine_audit
        res = layer.process(s['data'])
        print(f"Engine Selected: {res.get('engine_audit')}")
        print(f"Verdict: {res.get('final_verdict')}")

if __name__ == "__main__":
    # Ensure keys are set for the test session if they were just set at user level
    if not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = "AIzaSyCc-1iZAa45TyGRqCE-BrKcizDVb3ghMTY"
    
    test_routing()
