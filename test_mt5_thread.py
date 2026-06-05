import asyncio
import MetaTrader5 as mt5
import threading

def test_mt5():
    print(f"Current thread: {threading.current_thread().name}")
    res = mt5.terminal_info()
    print(f"MT5 terminal info: {res}")
    return res

async def main():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return

    print("Testing MT5 on main thread...")
    test_mt5()

    print("\nTesting MT5 on background thread...")
    try:
        res = await asyncio.to_thread(test_mt5)
        if res is None:
            print("MT5 returned None in background thread (as expected by memory)")
        else:
            print("MT5 worked in background thread!")
    except Exception as e:
        print(f"MT5 raised exception in background thread: {e}")

    mt5.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
