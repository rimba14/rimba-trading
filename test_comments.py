import MetaTrader5 as mt5

if not mt5.initialize():
    print("Init failed")
    quit()

symbol = "EURUSD"
mt5.symbol_select(symbol, True)
tick = mt5.symbol_info_tick(symbol)

def test_order(comment_val):
    print(f"\nTesting with comment: '{comment_val}' (type: {type(comment_val)})")
    from gitagent_action_layer import get_action_layer
    result = get_action_layer().execute_smart_trade(symbol, mt5.ORDER_TYPE_BUY, 0.01, comment=comment_val)
    if result is None:
        err = mt5.last_error()
        print(f"FAILED. Error: {err}")
    else:
        print(f"SUCCESS. Retcode: {result.retcode}")


tests = [
    "Short",
    "This is a reasonably long comment text", # 38 chars
    "1234567890123456789012345678901", # 31 chars
    "12345678901234567890123456789012", # 32 chars
    None,
]

for t in tests:
    test_order(t)

mt5.shutdown()
