import time
import concurrent.futures

class ThreadPoolTest:
    def fetch_data(self, symbol):
        # mock sleep
        time.sleep(0.01)
        return symbol, 100.0, 1.5

    def run(self, watchlist):
        prices = {}
        atrs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(watchlist))) as ex:
            results = ex.map(self.fetch_data, watchlist)
            for symbol, price, atr in results:
                prices[symbol] = price
                atrs[symbol] = atr
        return prices, atrs

t = ThreadPoolTest()
start = time.time()
p, a = t.run([f"S_{i}" for i in range(50)])
print(f"Time: {time.time() - start:.4f}")
