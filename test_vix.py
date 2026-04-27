import yfinance as yf
try:
    vix = yf.Ticker('^VIX')
    hist = vix.history(period='5d')
    print("VIX History:")
    print(hist.tail())
    if not hist.empty:
        print(f"LATEST VIX: {hist['Close'].iloc[-1]}")
    else:
        print("VIX History is EMPTY")
except Exception as e:
    print(f"VIX Fetch FAILED: {e}")
