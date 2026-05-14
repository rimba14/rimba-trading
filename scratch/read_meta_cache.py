import sys
sys.path.append("C:/Sentinel_Project")
import git_arctic

def check_cache():
    store = git_arctic.get_arctic()
    lib = store['oracle_cache']
    print("Symbols in oracle_cache:", lib.list_symbols())
    for sym in ["NAS100_meta", "US2000_meta", "NAS100_kronos", "US2000_kronos", "NAS100_hmm", "US2000_hmm"]:
        if sym in lib.list_symbols():
            item = lib.read(sym)
            print(f"\n--- {sym} tail(2) ---")
            print(item.data.tail(2))

if __name__ == "__main__":
    check_cache()
