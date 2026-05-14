from arcticdb import Arctic

store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
lib = store["oracle_cache"]
meta_syms = [s for s in lib.list_symbols() if s.endswith("_meta")]

print("=== LIVE P SCORE & HMM REGIME CACHE ===")
for s in meta_syms[:15]:
    try:
        row = lib.read(s).data.iloc[-1]
        p = float(row["meta_conviction"])
        hmm = str(row["hmm_state"])
        status = "BLOCKED (Hysteresis Deadzone)" if 0.40 <= p <= 0.60 else "GATE BREACHED"
        print(f"[{s.replace('_meta','')}] HMM: {hmm:<7} | Blended P Score: {p:.4f} | Gate: {status}")
    except Exception as e:
        print(f"[{s}] Read Error: {e}")
