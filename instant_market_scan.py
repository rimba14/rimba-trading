import MetaTrader5 as mt5
import pandas as pd
import time
import json
from datetime import datetime


def run_scan():
    if not mt5.initialize():
        print("[FAIL] MT5 Initialization Failed")
        return

    # Watchlist mapped from vantage_execute.py
    symbols = [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF",
        "EURJPY+", "GBPJPY+", "EURGBP+", "EURAUD+", "GBPAUD+", "AUDJPY+", "CADJPY+", "EURCAD+", "EURCHF+", "GBPCHF+",
        "NAS100", "SP500", "DJ30", "UK100", "GER40", "HK50", "JPN225", "AUS200", "FRA40",
        "XAUUSD+", "XAGUSD", "CL-OIL", "NG-Cr", "XPTUSD", "XPDUSD", "NATGAS",
        "NVIDIA", "AAPL", "MSFT", "META", "GOOG", "TSLA", "AMAZON", "AVGO", "JPM", "GS", 
        "V", "AMD", "INTC", "QCOM", "NFLX", "DIS", "WMT", "COST", "CRM", "ORCL",
        "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD", "ADAUSD", "DOGEUSD"
    ]
    
    print(f"\n[SCAN] Initiating High-Precision Scan across {len(symbols)} Institutional Assets...")
    
    results = []
    for sym in symbols:
        info = mt5.symbol_info(sym)
        if not info: continue
        
        # Get basic momentum metrics using the core library
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 100)
        if rates is None or len(rates) < 50:
            continue
            
        df = pd.DataFrame(rates)
        df['close'] = df['close'].astype(float)
        
        # Super quick 14-RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # Quick SMA50 Distance
        df['sma_50'] = df['close'].rolling(window=50).mean()
        
        current_price = df['close'].iloc[-1]
        rsi_val = df['rsi_14'].iloc[-1]
        sma_val = df['sma_50'].iloc[-1]
        
        if pd.isna(rsi_val) or pd.isna(sma_val): continue
            
        dist_sma = ((current_price - sma_val) / sma_val) * 100
        
        spread = info.ask - info.bid
        
        results.append({
            "asset": sym,
            "price": current_price,
            "rsi": rsi_val,
            "dist_sma": dist_sma,
            "spread": spread
        })

    df_res = pd.DataFrame(results)
    if df_res.empty:
        print("[WARN] No market data available. Markets may be closed.")
        mt5.shutdown()
        return

    # Sort Top Oversold (BUY)
    buys = df_res.sort_values(by="rsi", ascending=True).head(5)
    # Sort Top Overbought (SELL)
    sells = df_res.sort_values(by="rsi", ascending=False).head(5)

    print("\n--- TOP BULLISH PROSPECTS (OVERSOLD) ---")
    for _, r in buys.iterrows():
        print(f"{r['asset']:>10} | Price: {r['price']:>8.2f} | RSI: {r['rsi']:>5.1f} | SMA50 Dist: {r['dist_sma']:>5.2f}%")

    print("\n--- TOP BEARISH PROSPECTS (OVERBOUGHT) ---")
    for _, r in sells.iterrows():
        print(f"{r['asset']:>10} | Price: {r['price']:>8.2f} | RSI: {r['rsi']:>5.1f} | SMA50 Dist: {r['dist_sma']:>5.2f}%")

    print(f"\n[COMPLETE] Scanned {len(df_res)} active symbols.")
    mt5.shutdown()

if __name__ == "__main__":
    run_scan()
