import json
import time
import logging
import sys
import yfinance as yf
from typing import Dict, Any, List
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server for Alternative Data Oracle
mcp = FastMCP("Sentinel Alt-Data Oracle")

@mcp.tool()
def fetch_unstructured_sentiment(symbol: str, asset_class: str) -> str:
    """
    Alternative Data Oracle Tool: Retrieves latest news headlines and unstructured social metrics.
    Used for Black Swan detection and sentiment-regime validation.
    """
    try:
        # 1. Fetch Headlines via yfinance
        ticker = yf.Ticker(symbol)
        news = ticker.news
        
        if not news:
            # Fallback for symbols that might not have direct news in yf (e.g. some forex/crypto)
            return json.dumps({
                "symbol": symbol,
                "status": "NO_DATA",
                "message": "No recent headlines found via primary ticker discovery.",
                "headlines": []
            })

        # 2. Package and Sanitize Headlines (Limit to 25)
        sanitized_news = []
        for item in news[:25]:
            sanitized_news.append({
                "title": item.get("title", ""),
                "publisher": item.get("publisher", ""),
                "link": item.get("link", ""),
                "providerPublishTime": item.get("providerPublishTime", 0),
                "type": item.get("type", "STORY")
            })

        # 3. Add Metric Metadata
        payload = {
            "symbol": symbol,
            "asset_class": asset_class,
            "count": len(sanitized_news),
            "headlines": sanitized_news,
            "timestamp_utc": int(time.time())
        }

        return json.dumps(payload, indent=2)

    except Exception as e:
        return json.dumps({"status": "ERROR", "message": f"Sentiment Fetch Failed: {str(e)}"})

if __name__ == "__main__":
    mcp.run()
