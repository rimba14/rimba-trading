import math

def test_scaling(p_final, GLOBAL_TEMPERATURE=3.0):
    try:
        p_clamped = min(max(p_final, 0.0001), 0.9999)
        logit = math.log(p_clamped / (1 - p_clamped))
        scaled_p = 1 / (1 + math.exp(-logit * GLOBAL_TEMPERATURE))
        return scaled_p
    except Exception as e:
        print(f"Error: {e}")
        return p_final

test_cases = [0.51, 0.55, 0.60, 0.45, 0.40]
for p in test_cases:
    scaled = test_scaling(p)
    print(f"P: {p:.3f} -> Scaled: {scaled:.3f} (Delta: {abs(scaled-0.5):.3f} vs {abs(p-0.5):.3f})")
