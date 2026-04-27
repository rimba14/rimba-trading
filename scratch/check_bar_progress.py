
import sys
sys.path.append(r"C:\Sentinel_Project")
import MetaTrader5 as mt5
from gitagent_bars import InformationBarStreamer
import time

def check_bar_progress():
    print("=== DOLLAR BAR PROGRESS CHECK ===")
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    symbols = ["BTCUSD", "EURUSD", "XAUUSD"]
    streamer = InformationBarStreamer(symbols)
    
    # We'll poll for 10 seconds and see how much volume we accumulate
    start_time = time.time()
    print(f"Polling volume for 10 seconds... (Threshold: ${streamer.threshold:,.0f})")
    
    # Manually run the logic from stream_bars for 10 seconds
    while time.time() - start_time < 10:
        for symbol in symbols:
            ticks = mt5.copy_ticks_from(symbol, int(time.time() - 60), 100, mt5.COPY_TICKS_ALL)
            if ticks is not None and len(ticks) > 0:
                for tick in ticks:
                    price = tick[3] if tick[3] > 0 else tick[1]
                    volume = tick[7] if tick[7] > 0 else tick[4]
                    dollar_value = price * volume
                    streamer.tallies[symbol] += dollar_value
        time.sleep(1)

    for s in symbols:
        prog = streamer.tallies[s]
        pct = (prog / streamer.threshold) * 100
        print(f"{s}: ${prog:,.2f} accumulated ({pct:.6f}% of threshold)")

    mt5.shutdown()

if __name__ == "__main__":
    check_bar_progress()
