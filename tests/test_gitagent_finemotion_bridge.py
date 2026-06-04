import sys
from unittest.mock import MagicMock
import pytest

# Mock finemotion before importing the bridge
mock_emotion = MagicMock()
sys.modules['finemotion'] = MagicMock()
sys.modules['finemotion'].emotion = mock_emotion

from gitagent_finemotion_bridge import FinEmotionBridge

@pytest.fixture(autouse=True)
def reset_mock():
    mock_emotion.reset_mock(side_effect=True, return_value=True)

def test_instantiation():
    bridge = FinEmotionBridge()
    assert bridge is not None

def test_get_emotion_vector():
    expected_vector = {
        'fear': 0.1, 'anger': 0.1, 'trust': 0.1, 'surprise': 0.1,
        'sadness': 0.1, 'disgust': 0.1, 'joy': 0.1, 'anticipation': 0.1
    }
    mock_emotion.get_emotion.return_value = expected_vector
    bridge = FinEmotionBridge()
    vec = bridge.get_emotion_vector("test text")
    assert vec == expected_vector
    mock_emotion.get_emotion.assert_called_with("test text")

def test_get_emotion_vector_error_handling():
    mock_emotion.get_emotion.side_effect = Exception("error")
    bridge = FinEmotionBridge()
    vec = bridge.get_emotion_vector("test text")
    assert all(v == 0.0 for v in vec.values())

def test_get_dominant_emotion():
    mock_emotion.get_mixed_emotion.return_value = "joy"
    bridge = FinEmotionBridge()
    emotion_label = bridge.get_dominant_emotion("happy day")
    assert emotion_label == "joy"
    mock_emotion.get_mixed_emotion.assert_called_with("happy day")

def test_get_consolidated_bias():
    mock_emotion.get_emotion.return_value = {
        'trust': 0.5, 'joy': 0.5, 'anticipation': 0.5, 'surprise': 1.0,
        'fear': 0.0, 'anger': 0.0, 'sadness': 0.0, 'disgust': 0.0
    }
    bridge = FinEmotionBridge()
    # pos = 0.5 + 0.5 + 0.5 + (1.0 * 0.5) = 2.0
    # neg = 0.0
    # bias = 2.0 -> clamped to 1.0
    bias = bridge.get_consolidated_bias("very positive")
    assert bias == 1.0
