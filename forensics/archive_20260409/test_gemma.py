import time
from gitagent_gemma_connector import GemmaContextLayer

print("--- INITIALIZING GEMMA-4 TEST ---")
ctx = GemmaContextLayer()

# Mock cognition input
cognition_data = {
    'regime': 'Trend-Up (Hysteresis)',
    'confidence': 0.8234,
    'cognition_factor': 0.45
}

start_time = time.time()
result = ctx.process(cognition_data)
end_time = time.time()

print("\n--- TEST RESULTS ---")
print(f"Verdict: {result.get('final_verdict')}")
print(f"Reasoning: {result.get('reasoning')}")
print(f"Inference Time: {end_time - start_time:.2f} seconds")
print(f"Engine: {result.get('engine')}")
