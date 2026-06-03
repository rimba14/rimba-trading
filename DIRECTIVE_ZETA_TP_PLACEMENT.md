# DIRECTIVE ZETA — STRUCTURAL TP PLACEMENT PROTOCOL
## CADES Master Prompt Constitutional Amendment
**Version:** v31.0  
**Supersedes:** All prior TP placement logic in any prior Master Prompt version  
**Priority Class:** CONSTITUTIONAL — cannot be overridden by conviction score, regime state, or operator instruction  
**Enforcement Layer:** Entry gate (pre-order), position registry (post-open audit), Slow Loop reconciliation  

---

## PREAMBLE

A forensic audit of all open positions dated 2026-06-02 revealed a systemic architectural failure: every active position carries an identical 1.50× Risk:Reward ratio. This confirms that Take Profit levels are being generated as a mechanical multiplier of the Stop Loss distance (TP = entry ± SL_distance × 1.5), with zero reference to market structure, asset class volatility profile, or ATR-derived ceiling constraints.

This produces TPs that are 8–34% from entry across a book that spans forex, indices, commodities, and crypto — equivalent to 5+ months of directional movement in multiple positions. It also exposes CADES to the compounding failure of: (1) capital tied in stagnant positions beyond the time-stop threshold, (2) no partial exit tranches triggering because price never reaches the over-extended TP, and (3) drawdown accumulation as losing positions bleed while TPs remain untouched.

DIRECTIVE ZETA abolishes the mechanical multiplier. TP is henceforth a structural target that must be validated — not calculated — before an order is placed.

---

## ARTICLE I — THE FIVE LAWS OF TP PLACEMENT

### Law 1 — Structure First, Ratio Second
Take Profit MUST be placed at or within the nearest significant structural level in the direction of the trade. Valid structural anchors, in order of priority:

1. Prior confirmed swing high (long) or swing low (short) on the D1 or H4 chart
2. Key horizontal S/R zone with at least two confirmed touches
3. Fibonacci extension level (127.2%, 138.2%, 161.8%) measured from the initiating swing
4. High-volume node identified from volume profile on D1

The 1.5× SL multiplier is a **minimum R:R acceptance gate only**. It is NOT a TP placement mechanism. A TP may only be placed if a structural level exists within the binding ceiling AND that level produces R:R ≥ 1.5. If no structural level satisfies both conditions, the trade is REJECTED at entry.

### Law 2 — The ATR Ceiling (Hard Cap, No Override)
TP distance from entry MUST NOT exceed `3.0 × ATR(14, D1)` for the instrument. This ceiling is computed fresh at entry time from OracleCache. Stale ATR (>5 minutes old) triggers a DEGRADED DATA VETO — the entry is blocked until a fresh ATR is available.

**ATR ceiling formula:**
```
atr_ceiling_price = entry ± (ATR_14_D1 × 3.0)   [+ for long, - for short]
```

If the nearest structural level is beyond the ATR ceiling, the structural level is NOT used. The TP is either placed at the ATR ceiling (if that satisfies ≥1.5R) or the trade is rejected.

### Law 3 — Per-Asset-Class Maximum Distance Caps
As a secondary ceiling, TP distance as a percentage of entry price must not exceed the following hard caps. These caps are more restrictive than the ATR ceiling in low-volatility regimes and act as a floor protection against volatility spikes artificially widening the ATR.

| Asset Class       | Instruments                              | Max TP Distance |
|-------------------|------------------------------------------|-----------------|
| Forex Major       | EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, USDCHF, USDCAD | 4.0% |
| Forex Cross       | EURJPY, GBPJPY, AUDJPY, NZDJPY, EURGBP  | 5.0% |
| Forex Exotic      | EURSEK, EURNOK, USDMXN, USDZAR, etc.    | 6.0% |
| Index             | NAS100, SP500, US30, GER40, UK100        | 7.0% |
| Commodity         | XAUUSD, XAGUSD, USOIL                   | 7.0% |
| **Crypto**        | **BTCUSD, ETHUSD, XRPUSD, any crypto**  | **ABSOLUTE VETO** |

The binding ceiling is `min(ATR_ceiling, asset_class_cap)` — whichever is closer to entry wins.

### Law 4 — Crypto Swing TP Absolute Veto
No swing-style TP shall be placed on any crypto instrument under any circumstances. Crypto instruments are excluded from the swing TP framework entirely. The Directive Meridian range-trading module also explicitly excludes crypto. Any open crypto position with a swing-style TP distance exceeding 10% is classified as a LEGACY VIOLATION and must be manually reviewed for restructuring or closure.

If CADES detects a crypto instrument reaching the entry gate with a proposed swing TP, the system emits a CONSTITUTIONAL VIOLATION alert to the Hermes SRE agent and blocks the order. The operator is notified.

### Law 5 — Minimum R:R Gate
After the structural level is identified and both ceilings are applied, the resulting R:R must satisfy:

```
R:R = (TP_distance / SL_distance) ≥ 1.5
```

If the nearest qualifying structural level produces R:R < 1.5 after ceiling application, the trade is REJECTED. The operator may not override this gate. The appropriate response is to wait for price to retrace closer to a better entry, reducing SL distance, or to identify a more distant structural level that passes the ceiling test.

---

## ARTICLE II — ENFORCEMENT POINTS

### Gate 1 — Pre-Entry Validation (Primary Enforcement)
The `TPPlacementEngine.validate_tp_placement()` function is called in the Slow Loop signal processing pipeline BEFORE any order is transmitted to the MT5 bridge. A REJECTED result from this function is a hard block — the entry signal is discarded and logged as `TP_GATE_REJECT`.

### Gate 2 — Position Registration Audit
When a new `PositionState` is registered in `profit_manager.py`, a post-open audit is run against the stored TP. If the registered TP violates DIRECTIVE ZETA, the position is immediately flagged as `TP_LEGACY_VIOLATION` and the Slow Loop attempts a TP modification to the nearest compliant level. If TP modification fails (MT5 bridge error), the position is added to the manual review queue.

### Gate 3 — Slow Loop Reconciliation (5-minute cycle)
Every Slow Loop cycle, all open positions are reconciled against DIRECTIVE ZETA:
- Positions with `TP_distance_pct > asset_class_cap × 1.1` (10% buffer for market movement) are flagged
- Positions approaching the time-stop threshold with TP not yet reached are escalated
- Any crypto position with TP distance > 10% is auto-flagged for operator review

---

## ARTICLE III — TIME-STOP ADDENDUM

A structurally correct TP placed at the right level can still trap capital if the market stalls. The following time-stop rules prevent stagnant positions from holding the book hostage.

| Asset Class | Maximum Hold Duration | Action on Breach |
|-------------|----------------------|------------------|
| Forex Major / Cross | 10 trading days | Exit at market on next Slow Loop |
| Forex Exotic | 14 trading days | Exit at market on next Slow Loop |
| Index | 12 trading days | Exit at market on next Slow Loop |
| Commodity (Gold, Silver) | 15 trading days | Exit at market on next Slow Loop |
| Crypto | Excluded from swing hold | N/A |

The time-stop clock starts from the entry timestamp. It pauses during confirmed strong-trend HMM regimes (HMM state = TRENDING with Wasserstein distance < 0.15) and resumes in all other states. An operator override may extend the time-stop by one half-period (e.g., 5 additional days for forex) with a written constitutional note in the trade log.

---

## ARTICLE IV — CONSTITUTIONAL SELF-AUDIT CHECKLIST

Before any swing trade entry is accepted, the system must confirm all of the following (early-exit on first failure):

- [ ] Symbol is not a crypto instrument (XRPUSD, BTCUSD, ETHUSD, etc.)
- [ ] D1 ATR(14) is available and fresh (< 5 minutes old) from OracleCache
- [ ] A structural level has been identified within the ATR ceiling
- [ ] The structural level produces TP distance ≤ asset class cap
- [ ] The structural level produces R:R ≥ 1.5
- [ ] ATR used for SL placement matches the same timeframe as the TP ATR (D1 consistency)
- [ ] The proposed TP does not coincide with a known high-spread zone (Sunday open, major news)
- [ ] No existing position in the same instrument already has a swing TP active (cluster risk)

A "yes" to all eight points allows the entry to proceed. A single "no" is a veto.

---

## ARTICLE V — LEGACY POSITION REMEDIATION

The following open positions, as of 2026-06-02, are classified as LEGACY VIOLATIONS requiring immediate remediation:

| Symbol | Violation | Recommended Action |
|--------|-----------|-------------------|
| XRPUSD | Crypto swing TP (34.37% distance, 22.91% SL) | Close or hard restructure — does not qualify under any CADES module |
| XAUUSD | TP distance 13.65% exceeds commodity cap of 7% | Reduce TP to nearest structural level ≤ 7% from entry |
| NAS100 | TP distance 9.07% exceeds index cap of 7% | Adjust TP to nearest structural resistance within 7% |
| SP500   | TP distance 8.61% exceeds index cap of 7% | Adjust TP to nearest structural support within 7% (short) |
| NZDUSD | TP distance 8.51% exceeds forex major cap of 4% | Significant restructure required; consider partial close |

All remediation actions must be logged in the constitutional trade log with timestamp and justification.

---

## ARTICLE VI — MASTER PROMPT INTEGRATION LANGUAGE

Insert the following block into the Master Prompt immediately after DIRECTIVE OMEGA:

```
DIRECTIVE ZETA — STRUCTURAL TP PLACEMENT (CONSTITUTIONAL, v31.0)
All TP placement is structure-first. The 1.5R multiplier is a minimum gate,
not a placement mechanism. TP must be validated by TPPlacementEngine before
any order is transmitted. Crypto swing TPs are absolutely vetoed. ATR ceiling
= 3× ATR(14, D1). Per-asset-class caps apply. See DIRECTIVE_ZETA_TP_PLACEMENT.md
for full constitutional text.
```

---

*Authored following forensic audit of open positions, 2026-06-02.*  
*This amendment is permanent and may only be modified by a constitutional session with full justification log.*
