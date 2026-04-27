import time
import json
from deepseek_bridge import DeepSeekBridge
import pandas as pd
from typing import Tuple, Dict, Any
from gitagent_dexter_bridge import DexterBridge
from gitagent_owl_bridge import OwlBridge
from gitagent_semantic_memory import SemanticMemory
from gitagent_news_perceiver import NewsPerceiver
from gitagent_social_oracle import SocialOracle
from gitagent_finemotion_bridge import FinEmotionBridge
from stable_baselines3 import PPO
import numpy as np

class SentimentOracle:
    """
    DeepSeek Market Oracle (Emulates Banushev BERT layer)
    """
    def __init__(self):
        self.bridge = DeepSeekBridge()
        self.dexter = DexterBridge()
        self.owl = OwlBridge()
        self.memory = SemanticMemory()
        self.news_perceiver = NewsPerceiver()
        self.social_oracle = SocialOracle()
        self.emotion_bridge = FinEmotionBridge()
        try:
            self.alpha_optimizer = PPO.load("C:\\Sentinel_Project\\ppo_alpha_optimizer")
        except:
            self.alpha_optimizer = None
        self.cache = {} # sym -> {score, ts}

    def get_market_pulse(self, symbol: str, df: pd.DataFrame, macro_context: str = "") -> float:
        # Rate limit: Once per hour per symbol
        now = time.time()
        if symbol in self.cache and (now - self.cache[symbol]['ts']) < 3600:
            return self.cache[symbol]['score']

        # Enhanced Prompt: Multi-source Grounding
        last_ret = (df['close'].iloc[-1] / df['close'].iloc[-12] - 1.0) * 100
        prompt = f"""Analyze the Sentiment Pulse for {symbol}. 
Recent M15 Price Move: {last_ret:.2f}%.
MACRO CONTEXT (last30days): {macro_context}
Current VIX context: 15.0.
Act as a G10 Macro Analyst. Return a single JSON object with 'score' (-1.0 to 1.0) 
representing your conviction for the next 24 hours."""

        messages = [{"role": "user", "content": prompt}]
        response = self.bridge.chat_completion(messages)
        
        score = 0.0
        try:
            # Attempt to extract JSON if present
            if "{" in response:
                payload = json.loads(response[response.find("{"):response.rfind("}")+1])
                score = float(payload.get('score', 0.0))
            else:
                # Naive text-based fallback
                if "bullish" in response.lower(): score = 0.5
                if "bearish" in response.lower(): score = -0.5
        except:
            score = 0.0

        # Phase 175: Fundamental Blending (Dexter Integration)
        fund_data = self.dexter.get_fundamental_health(symbol)
        fund_weight = 0.5 if fund_data['verdict'] != "NEUTRAL" else 0.0
        
        # Adjust score by health factor (-1.0 to 1.0 mapping)
        health_mod = (fund_data['health_score'] - 50.0) / 50.0 
        score = (score * (1.0 - fund_weight)) + (health_mod * fund_weight)

        # Phase 178: Visual Confirmation (Owl Integration)
        vis_confirm = self.owl.get_visual_confirmation(symbol)
        # Visual weight: 0.2 (Confirmation layer)
        score = (score * 0.8) + (((vis_confirm - 0.5) * 2.0) * 0.2)

        # Phase 209: FinLLM Perception (News Integration)
        news_data = self.news_perceiver.get_latest_news_sentiment(symbol)
        if news_data.get('count', 0) > 0:
            # News weight: 0.15 (Bias layer)
            score = (score * 0.85) + (news_data['pulse'] * 0.15)
            print(f"[SENTIMENT] News-adjusted Score for {symbol}: {score:.4f} (Pulse: {news_data['pulse']})")

        # Phase 211/221: Social Sentiment (FinEmotion High-Res Upgrade)
        # Mock social text for analysis
        social_text = f"Markets are reacting strongly to {symbol} today. Sentiment is shifting."
        social_score = self.emotion_bridge.get_consolidated_bias(social_text)
        emotion_label = self.emotion_bridge.get_dominant_emotion(social_text)
        
        # Phase 215/220: Dynamic RL Weighting (Restored)
        if self.alpha_optimizer:
            # Map technical score to tech_pulse
            tech_pulse = score 
            # Derive macro_pulse from VIX/last_ret heuristic (0.0 center)
            macro_pulse = (15.0 - 20.0) / 20.0 # simple VIX baseline adjustment
            
            obs = np.array([tech_pulse, news_data['pulse'], social_score, macro_pulse], dtype=np.float32)
            action, _ = self.alpha_optimizer.predict(obs, deterministic=True)
            # Normalize weights
            weights = action / (np.sum(action) + 1e-8)
            score = np.dot(weights, obs)
            print(f"[SENTIMENT] RL-Grounded Composite Score for {symbol}: {score:.4f} (Emotion: {emotion_label})")
        else:
            # Fallback to static weights if RL model not found
            score = (score * 0.90) + (social_score * 0.10)
            if social_score != 0.0:
                print(f"[SENTIMENT] Social-adjusted Score for {symbol}: {score:.4f} (Emotion: {emotion_label})")

        self.cache[symbol] = {'score': score, 'ts': now}
        return score

_SENTIMENT_ORACLE = SentimentOracle()

def get_sentiment_pulse(symbol: str, df: pd.DataFrame) -> float:
    return _SENTIMENT_ORACLE.get_market_pulse(symbol, df)
