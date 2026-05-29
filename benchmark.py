import time
import concurrent.futures
from unittest.mock import MagicMock

def mt5_symbol_info_tick(symbol):
    tick_mock = MagicMock()
    tick_mock.bid = 100.0
    tick_mock.ask = 100.2
    return tick_mock

def _arctic_read(key):
    time.sleep(0.01)
    meta_item = MagicMock()
    meta_item.data.iloc = [MagicMock()]
    meta_item.data.iloc[-1].get.return_value = 1.5
    return meta_item

watchlist = [f"SYM_{i}" for i in range(50)]
_LAST_CYCLE_PRICES = {}
_LAST_CYCLE_ATRs = {}

def original_code():
    for symbol in watchlist:
        try:
            tick = mt5_symbol_info_tick(symbol)
            if tick:
                _LAST_CYCLE_PRICES[symbol] = (tick.bid + tick.ask) / 2
            meta_item = _arctic_read(f"{symbol}_meta")
            if meta_item is not None:
                _LAST_CYCLE_ATRs[symbol] = float(meta_item.data.iloc[-1].get("atr", 0.0))
        except Exception as e:
            pass

def optimized_code():
    def process_symbol(symbol):
        try:
            tick = mt5_symbol_info_tick(symbol)
            if tick:
                _LAST_CYCLE_PRICES[symbol] = (tick.bid + tick.ask) / 2
            meta_item = _arctic_read(f"{symbol}_meta")
            if meta_item is not None:
                _LAST_CYCLE_ATRs[symbol] = float(meta_item.data.iloc[-1].get("atr", 0.0))
        except Exception as e:
            pass
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(watchlist))) as executor:
        executor.map(process_symbol, watchlist)

start = time.time()
original_code()
print(f"Original: {time.time() - start:.4f}s")

start = time.time()
optimized_code()
print(f"Optimized: {time.time() - start:.4f}s")
