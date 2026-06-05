"""
sentinel_dashboard.py - ADAPTIVE SENTINEL VISUAL COMMAND CENTER (v17.3)
Machine A only. Strictly read-only. Decoupled from all execution threads.
"""
import streamlit as st
import pandas as pd
import os
import json
import time
import concurrent.futures
from arcticdb import Arctic
from datetime import datetime, timezone
from pathlib import Path

import sentinel_config

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SENTINEL COMMAND CENTER v17.3",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
.main, .stApp { background-color: #05070a; color: #e0e0e0; }
[data-testid="stHeader"] { background: rgba(0,0,0,0); }
.stMetric {
    background: linear-gradient(135deg, #0f1923 0%, #111827 100%);
    border: 1px solid #1e3a5f; border-radius: 10px; padding: 16px;
}
h1, h2, h3 { color: #38bdf8 !important; }
.stDataFrame, .stTable { border: 1px solid #1f2937; border-radius: 8px; }
.stAlert { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path("C:/Sentinel_Project")
ARCTIC_TIMEOUT = 0.3   # 300 ms — Phase 1
SHAP_DIR      = PROJECT_ROOT / "shap_diagnostics"
HALT_PATH     = PROJECT_ROOT / "halt_signal.json"
DIAG_DIR      = PROJECT_ROOT / "pending_diagnostics"
EPISTEMIC_GATE = 0.82

SAMPLE_WATCHLIST = [
    "BTCUSD", "ETHUSD", "SOLUSD",
    "NAS100", "SP500", "DJ30",
    "XAUUSD", "EURUSD", "GBPUSD",
]

# ── ArcticDB (read-only, 300 ms timeout) ──────────────────────────────────────
@st.cache_resource(ttl=30)
def get_oracle_lib():
    try:
        ac = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
        if "oracle_cache" in ac.list_libraries():
            return ac["oracle_cache"]
    except Exception as e:
        st.error(f"ArcticDB connection failed: {e}")
    return None


def _arc_read(lib, key: str):
    """Thread-safe ArcticDB read with 300 ms hard cap."""
    if lib is None:
        return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(lib.read, key)
        try:
            return fut.result(timeout=ARCTIC_TIMEOUT)
        except concurrent.futures.TimeoutError:
            return None
        except Exception:
            return None


def _arc_read_batch(lib, keys: list):
    """Parallel ArcticDB read with 300 ms hard cap per read."""
    if lib is None or not keys:
        return {}
    results = {}
    # Use a pool size capped at 20 to avoid over-allocation on large watchlists
    pool_size = min(len(keys), 20)
    with concurrent.futures.ThreadPoolExecutor(max_workers=pool_size) as ex:
        fut_to_key = {ex.submit(lib.read, k): k for k in keys}
        try:
            for fut in concurrent.futures.as_completed(fut_to_key, timeout=ARCTIC_TIMEOUT + 0.1):
                key = fut_to_key[fut]
                try:
                    results[key] = fut.result()
                except Exception:
                    results[key] = None
        except concurrent.futures.TimeoutError:
            # If batch timeout is hit, we still return whatever we gathered
            pass
        except Exception:
            pass
    # Ensure all keys are in results
    for k in keys:
        if k not in results:
            results[k] = None
    return results


# ── Header ─────────────────────────────────────────────────────────────────────
col_title, col_clock = st.columns([4, 1])
with col_title:
    st.title("🛡️ SENTINEL | Visual Command Center")
    st.caption("v17.3 Decoupled Production Build | Machine A — Read-Only")
with col_clock:
    st.metric("UTC Clock", datetime.now(timezone.utc).strftime("%H:%M:%S"))

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚡ System Status")
    st.success(f"Watchlist: {len(sentinel_config.WATCHLIST)} assets resolved")

    if HALT_PATH.exists():
        halt = json.loads(HALT_PATH.read_text())
        st.error(f"🛑 GLOBAL HALT\n{halt.get('reason','?')}")
    else:
        st.success("✅ Matrix: RUNNING")

    st.divider()
    # PSR diagnostics
    psr_files = list(DIAG_DIR.glob("psr_fail_*.json")) if DIAG_DIR.exists() else []
    if psr_files:
        st.warning(f"⚠️ {len(psr_files)} PSR_DEGRADATION ticket(s) pending SRE")
    else:
        st.info("PSR: Healthy (no SRE tickets)")

    st.divider()
    refresh_rate = st.slider("Auto-refresh (s)", 5, 60, 10)
    if st.button("🔄 Manual Refresh"):
        st.rerun()

lib = get_oracle_lib()

# ── Row 1: HMM Radar + Fast Loop Matrix ───────────────────────────────────────
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("📡 Slow Loop — HMM Radar")
    hmm_rows = []
    hmm_keys = [f"{sym}_hmm" for sym in SAMPLE_WATCHLIST]
    hmm_data = _arc_read_batch(lib, hmm_keys)

    for sym in SAMPLE_WATCHLIST:
        item = hmm_data.get(f"{sym}_hmm")
        if item is not None:
            row = item.data.iloc[-1]
            age = time.time() - float(row.get("timestamp", 0))
            stale = age > 900
            hmm_rows.append({
                "Symbol":    sym,
                "Regime":    row.get("state", "?"),
                "Prob":      f"{float(row.get('prob', 0)):.2%}",
                "ATR":       f"{float(row.get('atr', 0)):.5f}",
                "Age (s)":   f"{age:.0f}",
                "Fresh":     "⚠️ STALE" if stale else "✅",
            })
    if hmm_rows:
        st.dataframe(pd.DataFrame(hmm_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Awaiting Slow Loop cache commits…")

with col_r:
    st.subheader("⚡ Fast Loop — Meta-Conviction Matrix")
    meta_rows = []
    meta_keys = [f"{sym}_meta" for sym in SAMPLE_WATCHLIST]
    meta_data = _arc_read_batch(lib, meta_keys)

    for sym in SAMPLE_WATCHLIST:
        item = meta_data.get(f"{sym}_meta")
        if item is not None:
            row   = item.data.iloc[-1]
            p     = float(row.get("meta_conviction", 0.5))
            norm  = abs(p - 0.5) + 0.5
            d_int = int(row.get("primary_dir", 0))
            meta_rows.append({
                "Symbol":    sym,
                "Direction": "BUY" if d_int == 1 else ("SELL" if d_int == -1 else "HOLD"),
                "Conviction":f"{p:.4f}",
                "Gate":      "✅ PASS" if norm >= EPISTEMIC_GATE else "❌ BLOCKED",
                "HMM":       row.get("hmm_state", "?"),
            })
    if meta_rows:
        st.dataframe(pd.DataFrame(meta_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Awaiting Meta-Model cache commits…")

# ── Row 2: SHAP Concept Drift Monitor ─────────────────────────────────────────
st.divider()
st.subheader("🧠 SHAP Diagnostics — Concept Drift Monitor")
if SHAP_DIR.exists():
    diag_rows = []
    for jf in sorted(SHAP_DIR.glob("*.json")):
        try:
            data = json.loads(jf.read_text())
            weights = data.get("weights", {})
            max_f   = max(weights, key=lambda k: abs(weights[k]), default="?")
            max_w   = abs(weights.get(max_f, 0))
            diag_rows.append({
                "Symbol":       data.get("symbol", jf.stem),
                "Conviction":   f"{data.get('conviction', 0):.4f}",
                "Top Feature":  max_f,
                "Weight":       f"{max_w:.2%}",
                "Drift":        "🚨 DRIFT" if data.get("concept_drift") else "✅ OK",
                "Top Pos":      str(data.get("top_pos", [])[:2]),
                "Top Neg":      str(data.get("top_neg", [])[:2]),
            })
        except Exception:
            pass
    if diag_rows:
        st.dataframe(pd.DataFrame(diag_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No SHAP diagnostics found in shap_diagnostics/")
else:
    st.info("shap_diagnostics/ not yet created.")

# ── Row 3: Pending Signals ─────────────────────────────────────────────────────
st.divider()
st.subheader("📬 Pending Signal Queue")
sig_dir = PROJECT_ROOT / "pending_signals"
if sig_dir.exists():
    sigs = list(sig_dir.glob("*.json"))
    if sigs:
        sig_rows = []
        for sf in sorted(sigs, key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
            try:
                d = json.loads(sf.read_text())
                age = time.time() - float(d.get("timestamp", 0))
                sig_rows.append({
                    "File":      sf.name,
                    "Symbol":    d.get("symbol", "?"),
                    "Direction": d.get("direction", "?"),
                    "Conviction":f"{d.get('kronos_conviction', 0):.4f}",
                    "HMM":       d.get("hmm_state", "?"),
                    "Age (s)":   f"{age:.0f}",
                    "Stale":     "⚠️" if age > 900 else "✅",
                })
            except Exception:
                pass
        st.dataframe(pd.DataFrame(sig_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Signal queue empty.")
else:
    st.info("pending_signals/ not yet created.")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption(f"Last UI Sync: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC | "
           f"Auto-refresh in {refresh_rate}s")
time.sleep(refresh_rate)
st.rerun()
