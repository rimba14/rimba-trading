import sys
import os

# Ensure local FinEmotion repo is in path
FINEMOTION_PATH = "C:\\Sentinel_Project\\FinEmotion"
if FINEMOTION_PATH not in sys.path:
    sys.path.append(FINEMOTION_PATH)

from finemotion import emotion
from typing import Dict, Any

class FinEmotionBridge:
    """
    Bridge for the AI4Finance FinEmotion library.
    Provides 8D emotional vector analysis for financial texts.
    Dimensions: fear, anger, trust, surprise, sadness, disgust, joy, anticipation
    """
    def __init__(self):
        # We assume dependencies (spacy) were installed during Phase 221 initialization
        pass

    def get_emotion_vector(self, text: str) -> Dict[str, float]:
        """
        Analyzes text and returns an 8D emotion vector.
        """
        try:
            # get_emotion returns the actual 8D Dict
            vector = emotion.get_emotion(text)
            if not isinstance(vector, dict):
                return {
                    'fear': 0.0, 'anger': 0.0, 'trust': 0.0, 'surprise': 0.0,
                    'sadness': 0.0, 'disgust': 0.0, 'joy': 0.0, 'anticipation': 0.0
                }
            return vector
        except Exception as e:
            print(f"[FINEMOTION] Analysis Error: {e}")
            return {
                'fear': 0.0, 'anger': 0.0, 'trust': 0.0, 'surprise': 0.0,
                'sadness': 0.0, 'disgust': 0.0, 'joy': 0.0, 'anticipation': 0.0
            }

    def get_dominant_emotion(self, text: str) -> str:
        """
        Returns the top/mixed emotion as a string.
        """
        try:
            return emotion.get_mixed_emotion(text)
        except:
            return "neutral"

    def get_consolidated_bias(self, text: str) -> float:
        """
        Consolidates the 8D vector into a single scalar bias (-1.0 to 1.0).
        Positive: Trust, Joy, Anticipation, Surprise (weighted)
        Negative: Fear, Anger, Sadness, Disgust (weighted)
        """
        vec = self.get_emotion_vector(text)
        pos = vec.get('trust', 0) + vec.get('joy', 0) + vec.get('anticipation', 0) + (vec.get('surprise', 0) * 0.5)
        neg = vec.get('fear', 0) + vec.get('anger', 0) + vec.get('sadness', 0) + vec.get('disgust', 0)
        
        # Simple net bias, clamped
        bias = pos - neg
        return max(-1.0, min(1.0, bias))

if __name__ == "__main__":
    # Test logic
    bridge = FinEmotionBridge()
    test_text = "The stock market is extremely volatile today, investors are fearful of a crash."
    print(f"Test Text: {test_text}")
    print(f"Vector: {bridge.get_emotion_vector(test_text)}")
    print(f"Consolidated Bias: {bridge.get_consolidated_bias(test_text)}")
