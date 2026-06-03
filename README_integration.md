# DIRECTIVE ZETA — Integration & Deployment Guide
## CADES v25.1 — TP Placement Engine

---

## Files in this package

| File | Purpose |
|------|---------|
| `DIRECTIVE_ZETA_TP_PLACEMENT.md` | Constitutional amendment — the law |
| `tp_placement_engine.py` | Standalone TPPlacementEngine module — drop into your codebase |
| `profit_manager_tp_patch.py` | Section-by-section patch for profit_manager.py v25.0 |

---

## Deployment order

### Step 1 — Drop in the engine
Copy `tp_placement_engine.py` to the same directory as `profit_manager.py` on Oracle VPS.

### Step 2 — Apply the patch to profit_manager.py
Open `profit_manager.py` and apply the four sections from `profit_manager_tp_patch.py`:

```
Section A → top of file (imports)
Section B → ProfitManager.__init__() — add after existing component init
Section C → modify your register_position() method
Section D → add _reconcile_tp_compliance() as a new method
Section E → add _apply_time_stop_dampening() to ExitScoreEngine or profit_manager
Section F → add run_legacy_violation_audit() as a new method
```

### Step 3 — Wire the Slow Loop
In your Slow Loop orchestrator, add one call:
```python
profit_manager._reconcile_tp_compliance()
```
This runs every 5-minute cycle alongside your existing Slow Loop logic.

### Step 4 — Wire startup audit
In your application startup sequence, after MT5 position sync:
```python
summary = profit_manager.run_legacy_violation_audit()
logger.info(f"ZETA startup audit: {summary}")
```

### Step 5 — Wire the entry gate
In your signal pipeline (wherever you currently call mt5_bridge.open_position()),
add the gate BEFORE the broker call:
```python
result = profit_manager.tp_engine.validate_tp_placement(
    symbol=symbol, entry=entry, sl=sl,
    proposed_tp=proposed_tp, direction=direction
)
if not result.is_valid:
    logger.error(f"TP_GATE_REJECT: {result.rejection_reason}")
    return   # block the entry
tp_to_use = result.final_tp  # use this — it may have been adjusted
```

---

## OracleCache interface requirements
The engine calls these methods on your existing OracleCache:

```python
oracle_cache.get_atr(symbol, timeframe, period, max_age_seconds) -> float | None
oracle_cache.get_bars(symbol, timeframe, count) -> list[dict] | None
   # Each dict must have keys: "high", "low", "close", "open", "time"
oracle_cache.get_hmm_state(symbol) -> str   # "TRENDING", "RANGING", etc.
oracle_cache.get_wasserstein_distance(symbol) -> float | None
```

If your OracleCache uses different method names, create a thin adapter class.

---

## Immediate action — legacy positions (2026-06-02)

| Symbol | Action |
|--------|--------|
| XRPUSD | Close or restructure — crypto veto is absolute |
| XAUUSD | Manually move TP to nearest structural resistance ≤ $4,810 (7% from $4,495) |
| NAS100 | Move TP to nearest structural resistance ≤ ~32,900 (7% from $30,659) |
| SP500  | Move TP to nearest structural support ≥ ~7,170 (7% from $7,608 short) |
| NZDUSD | Move TP to nearest structural resistance ≤ ~0.616 (4% from $0.5925) |

EURJPY, EURSEK, NZDJPY, AUDJPY — within tolerance, no immediate action needed.

---

## Testing
Before deploying to Oracle VPS, run the test suite on Machine B:
```bash
python -m pytest test_tp_placement_engine.py -v
```
Key test cases to verify:
- XRPUSD → rejected (crypto veto)
- XAUUSD @ 13.65% TP → rejected (commodity cap)
- EURJPY @ 3.35% TP → accepted
- ATR unavailable → rejected (degraded data)
- TP adjusted to structural level → is_valid=True, adjusted=True
