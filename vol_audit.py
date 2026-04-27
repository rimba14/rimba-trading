import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def get_volatility(symbol):
    if not mt5.initialize(): return 0
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 10)
    if rates is None or len(rates) == 0: return 0
    df = pd.DataFrame(rates)
    # Simple Volatility: (High - Low) / Close
    df['range_pct'] = (df['high'] - df['low']) / df['close']
    return df['range_pct'].mean()

symbols = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF",
    "EURJPY", "GBPJPY", "EURGBP", "EURAUD", "GBPAUD", "AUDJPY", "CADJPY", "EURCAD", "EURCHF", "GBPCHF",
    "NAS100", "SP500", "DJ30", "UK100", "GER40", "HK50", "JPN225", "AUS200", "FRA40",
    "XAUUSD", "XAGUSD", "CL-OIL", "NG-Cr", "XPTUSD", "XPDUSD", "NATGAS",
    "NVIDIA", "AAPL", "MSFT", "META", "GOOG", "TSLA", "AMAZON", "AVGO", "JPM", "GS",
    "V", "AMD", "INTC", "QCOM", "NFLX", "DIS", "WMT", "COST", "CRM", "ORCL",
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD", "ADAUSD", "DOGEUSD"
]

if mt5.initialize():
    results = []
    for s in symbols:
        vol = get_volatility(s)
        results.append({"symbol": s, "vol_pct": vol})
    
    df_res = pd.DataFrame(results).sort_values(by="vol_pct", ascending=False)
    print(df_res.to_string())
    mt5.shutdown()
