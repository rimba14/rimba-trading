import time
import asyncio
import importlib.util
import sys
from unittest.mock import MagicMock

# Mock MetaTrader5
sys.modules['MetaTrader5'] = MagicMock()
mt5 = sys.modules['MetaTrader5']

tick_mock = MagicMock()
tick_mock.bid = 100.0
tick_mock.ask = 100.2
mt5.symbol_info_tick.return_value = tick_mock

import sentinel_slow_loop

# Mock arctic read to simulate slow DB read
def mock_arctic_read(key):
    time.sleep(0.01) # Simulating DB latency
    meta_item = MagicMock()
    meta_item.data.iloc = [MagicMock()]
    meta_item.data.iloc[-1].get.return_value = 1.5
    return meta_item

sentinel_slow_loop._arctic_read = mock_arctic_read

watchlist = [f"SYM_{i}" for i in range(50)] # Assuming 50 items

def run_loop_to_benchmark():
    for symbol in watchlist:
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                sentinel_slow_loop._LAST_CYCLE_PRICES[symbol] = (tick.bid + tick.ask) / 2
            meta_item = sentinel_slow_loop._arctic_read(f"{symbol}_meta")
            if meta_item is not None:
                sentinel_slow_loop._LAST_CYCLE_ATRs[symbol] = float(meta_item.data.iloc[-1].get("atr", 0.0))
        except Exception as e:
            pass

start_time = time.time()
run_loop_to_benchmark()
end_time = time.time()

print(f"Baseline time: {end_time - start_time:.4f} seconds")
