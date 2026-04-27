import base64
import os
import requests
import json
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from datetime import datetime
from gitagent_adaptive import fit_trend_channel

from gitagent_gemma_connector import GemmaContextLayer

class VisionPatternAgent:
    def __init__(self):
        self.gemma = GemmaContextLayer()
        self.temp_chart_path = "C:\\Sentinel_Project\\temp_chart.png"

    def generate_chart(self, df: pd.DataFrame, symbol: str):
        """Generates a high-fidelity OHLC chart with Trend Channels."""
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Draw Candlesticks
        prices = df['close'].values
        n = len(prices)
        x = np.arange(n)
        
        # Adaptive Trend Channels (Simplified for plotting)
        slope, intercept_at_end, upper_at_end, lower_at_end, pos = fit_trend_channel(prices)
        
        # Calculate full channel lines
        regression_full = slope * x + (intercept_at_end - slope * (n-1))
        std_dist = (upper_at_end - lower_at_end) / 4.0 # n_std=2.0 -> 4 sigma
        upper_full = regression_full + (2.0 * std_dist)
        lower_full = regression_full - (2.0 * std_dist)
        
        ax.plot(x, prices, color='cyan', alpha=0.8, label='Price')
        ax.plot(x, upper_full, 'r--', alpha=0.5, label='Upper Channel')
        ax.plot(x, lower_full, 'g--', alpha=0.5, label='Lower Channel')
        ax.fill_between(x, lower_full, upper_full, color='gray', alpha=0.1)
        
        ax.set_title(f"SENTINEL VISION AUDIT: {symbol}")
        ax.legend()
        
        plt.savefig(self.temp_chart_path)
        plt.close()
        return self.temp_chart_path

    def audit_visual_structure(self, df: pd.DataFrame, symbol: str, signal: str) -> dict:
        """Sends the chart to Gemini Vision for structural confirmation."""
        image_path = self.generate_chart(df, symbol)
        
        with open(image_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        prompt = f"""
        TECHNICAL VISION AUDIT: {symbol}
        CURRENT SIGNAL: {signal}
        
        TASK:
        1. Examine the provided OHLC chart and Trend Channels.
        2. Identify any classical chart patterns (Head & Shoulders, Wedges, Triangles, Double Tops/Bottoms).
        3. Confirm or Deny the current {signal} signal based on visual structure.
        4. Rate your Confidence from 0.0 to 1.0.
        
        RESPONSE FORMAT: [VERDICT] | [CONFIDENCE] | [RATIONALE]
        VERDICT: CONFIRMED, REJECTED, or NEUTRAL.
        """
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": encoded_image
                        }
                    }
                ]
            }]
        }
        
        try:
            output_text = self.gemma.process_vision(prompt, encoded_image)
            
            parts = output_text.split("|")
            verdict = parts[0].strip() if len(parts) > 0 else "NEUTRAL"
            confidence = float(parts[1].strip()) if len(parts) > 1 else 0.5
            rationale = parts[2].strip() if len(parts) > 2 else output_text
            
            return {
                "vision_verdict": verdict,
                "vision_confidence": confidence,
                "vision_rationale": rationale,
                "status": "success"
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "vision_verdict": "NEUTRAL", "vision_confidence": 0.0}

if __name__ == "__main__":
    # Test
    agent = VisionPatternAgent()
    df = pd.DataFrame({'close': np.linspace(10, 15, 50)})
    res = agent.audit_visual_structure(df, "TESTUSD", "BUY")
    print(res)
