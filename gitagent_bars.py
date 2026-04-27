import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import logging

# Configuration
DOLLAR_BAR_THRESHOLD = 10000000.0 # $10,000,000 USD (Directive: Stability in high-volume markets)

class InformationBarStreamer:
    """
    Event-Driven Data Pipeline (v15.8)
    Implements Volume/Dollar Bars to eliminate chronological noise.
    """
    def __init__(self, symbols, threshold=DOLLAR_BAR_THRESHOLD):
        self.symbols = symbols
        self.threshold = threshold
        self.tallies = {s: 0.0 for s in symbols}
        self.buffers = {s: [] for s in symbols}
        
        # Directive (v16.9 Fix): Sync with Broker Server Time (Lookback 5m)
        # Looking back 5 minutes ensures immediate live context without historical backlog.
        self.last_timestamps = {}
        for s in symbols:
            tick = mt5.symbol_info_tick(s)
            # Look back 60s (1m) from the last known tick
            self.last_timestamps[s] = (tick.time - 60) if tick else (int(time.time()) - 60)
            
        self.last_tick_msc = {s: 0 for s in symbols}

    def stream_bars(self):
        """Generates Information Bars as they form."""
        logging.info(f"[BARS] Starting Event-Driven Stream for {len(self.symbols)} symbols.")
        
        while True:
            for symbol in self.symbols:
                # Fetch ticks since last seen timestamp
                # Note: MT5 ticks are in seconds for copy_ticks_from, but we can use time_msc for filtering
                ticks = mt5.copy_ticks_from(symbol, self.last_timestamps[symbol], 1000, mt5.COPY_TICKS_ALL)
                
                if ticks is None or len(ticks) == 0:
                    continue
                
                # logging.debug(f"[BARS] {symbol}: Received {len(ticks)} ticks.")
                
                for tick in ticks:
                    # tick is a structured array row: (time, bid, ask, last, volume, time_msc, flags, volume_real)
                    if int(tick[5]) <= self.last_tick_msc[symbol]:
                        continue
                    self.last_tick_msc[symbol] = int(tick[5])
                    
                    price = float(tick[3]) if tick[3] > 0 else float(tick[1])
                    # MT5: volume is at index 4, volume_real at index 7
                    volume = float(tick[7]) if tick[7] > 0 else float(tick[4])
                    
                    # Directive (v16.9 Fix): Handle Zero-Volume Brokers
                    if volume <= 0:
                        volume = 1.0
                    
                    dollar_value = price * volume
                    self.tallies[symbol] += dollar_value
                    self.buffers[symbol].append(list(tick)) # Convert to list to avoid structured array issues in DataFrame
                    
                    if self.tallies[symbol] >= self.threshold:
                        logging.info(f"[BARS] {symbol}: Threshold Reached (${self.tallies[symbol]:,.0f} >= ${self.threshold:,.0f}). Yielding Bar.")
                        yield self._construct_bar(symbol)
                        # Reset for next bar
                        self.tallies[symbol] = 0.0
                        self.buffers[symbol] = []
                
                # Update last seen timestamp
                if len(ticks) >= 1000:
                    # High volume detected. Advance by 1 second to clear the buffer.
                    self.last_timestamps[symbol] = int(ticks[-1][0]) + 1
                else:
                    self.last_timestamps[symbol] = int(ticks[-1][0])

            time.sleep(0.01)

    def _construct_bar(self, symbol):
        """Converts raw tick buffer into an OHLCV Information Bar."""
        # Ticks were appended as lists of 8 elements
        cols = ['time', 'bid', 'ask', 'last', 'volume', 'time_msc', 'flags', 'real_volume']
        df = pd.DataFrame(self.buffers[symbol], columns=cols)
        
        # Use bid for prices in Forex, last for others
        price_col = 'last' if (df['last'] > 0).any() else 'bid'
        
        bar = {
            "symbol": symbol,
            "time": pd.to_datetime(df['time'].iloc[-1], unit='s'),
            "open": float(df[price_col].iloc[0]),
            "high": float(df[price_col].max()),
            "low": float(df[price_col].min()),
            "close": float(df[price_col].iloc[-1]),
            "tick_volume": int(len(df)),
            "real_volume": float(df['real_volume'].sum()),
            "dollar_value": float(self.tallies[symbol]),
            "type": "DOLLAR_BAR"
        }
        return bar

if __name__ == "__main__":
    # Test
    if mt5.initialize():
        streamer = InformationBarStreamer(["EURUSD", "BTCUSD"])
        for bar in streamer.stream_bars():
            print(f"[EVENT] New Bar for {bar['symbol']}: {bar['close']} (Vol: {bar['real_volume']})")
