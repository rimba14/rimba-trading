import MetaTrader5 as mt5
import json

def get_info():
    if not mt5.initialize():
        print("FAIL")
        return
    
    acc = mt5.account_info()
    if acc:
        print(json.dumps(acc._asdict(), indent=2))
    else:
        print("FAIL")
    
    mt5.shutdown()

if __name__ == "__main__":
    get_info()
