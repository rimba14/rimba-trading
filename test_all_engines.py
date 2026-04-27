import os
os.environ['GROQ_API_KEY'] = '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'
os.environ['GOOGLE_API_KEY'] = 'AIzaSyCc-1iZAa45TyGRqCE-BrKcizDVb3ghMTY'

from gitagent_context_layer import UniversalContextLayer

layer = UniversalContextLayer()

print("=== SENTINEL SWITCHBOARD FINAL TEST ===\n")

# --- GROQ: Fast-Lane (high conviction) ---
os.environ['SENTINEL_ENGINE'] = 'GROQ'
layer2 = UniversalContextLayer()
r1 = layer2.process({'regime': 'TREND', 'confidence': 0.92, 'urgency': 'HIGH', 'cognition_factor': 8.9})
print(f"GROQ   -> Engine: {r1['engine_audit']} | Verdict: {r1['final_verdict']}")
print(f"  Reason: {r1.get('reasoning', '')[:300]}")

# --- GEMINI: Cognitive Path (complex regime) ---
os.environ['SENTINEL_ENGINE'] = 'GEMINI'
layer3 = UniversalContextLayer()
r2 = layer3.process({'regime': 'BREAKOUT', 'confidence': 0.65, 'urgency': 'LOW', 'cognition_factor': 6.2})
print(f"GEMINI -> Engine: {r2['engine_audit']} | Verdict: {r2['final_verdict']}")

# --- LOCAL: Sovereign (default stable) ---
del os.environ['SENTINEL_ENGINE']
layer4 = UniversalContextLayer()
r3 = layer4.process({'regime': 'STABLE', 'confidence': 0.5, 'urgency': 'LOW', 'cognition_factor': 4.0})
print(f"LOCAL  -> Engine: {r3['engine_audit']} | Verdict: {r3['final_verdict']}")

print("\n=== ALL 3 ENGINES OPERATIONAL ===")
