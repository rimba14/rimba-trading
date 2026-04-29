import sys
import os
from pathlib import Path

# Robust Path Resolution: Ensure project root is in sys.path
SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Attempt to import the primary Arctic handler
try:
    import git_arctic
    DB_HANDLER = git_arctic
except ImportError:
    # Fallback to Arctic Polyfill if git_arctic is missing or broken
    try:
        import arctic_polyfill as DB_HANDLER
        # Mock get_arctic if polyfill uses a different name
        if not hasattr(DB_HANDLER, 'get_arctic'):
            def get_arctic_mock():
                return DB_HANDLER.Arctic("lmdb://./data/arctic_cache")
            DB_HANDLER.get_arctic = get_arctic_mock
    except ImportError:
        print("[FATAL] No ArcticDB handler found (tried git_arctic and arctic_polyfill).")
        sys.exit(1)
import pandas as pd
import json
from datetime import datetime, timezone

def get_market_summary():
    store = DB_HANDLER.get_arctic()
    lib = store['oracle_cache']
    
    # Expanded watchlist for comprehensive firing scan
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD", "US30", "NAS100", "GER40", "US500", "USOIL", "SOLUSD"]
    summary = []
    
    for symbol in symbols:
        try:
            # Get HMM State
            hmm_df = lib.read(f"{symbol}_hmm").data
            hmm_state = hmm_df['state'].iloc[-1]
            
            # Get Meta Conviction
            meta_df = lib.read(f"{symbol}_meta").data
            conviction = meta_df['meta_conviction'].iloc[-1]
            primary_dir = "BUY" if meta_df['primary_dir'].iloc[-1] == 1 else "SELL"
            
            # Calculate distance to firing gate (0.82)
            distance = 0.82 - conviction
            
            summary.append({
                "Symbol": symbol,
                "Regime": hmm_state,
                "Dir": primary_dir,
                "Conviction": round(conviction, 4),
                "Distance": round(distance, 4),
                "Status": "🔥 SIGNAL READY" if conviction >= 0.82 else "⏳ Warming Up"
            })
        except:
            continue
            
    # Sort by closest to firing
    summary = sorted(summary, key=lambda x: x['Distance'])
    return summary

if __name__ == "__main__":
    market_data = get_market_summary()
    print(json.dumps(market_data, indent=2))
