import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from gitagent_memory import EpisodicMemory
import gitagent_synthesis as syn
import os
import time
from datetime import datetime, timezone

# Institutional Data Sources
TRADES_FILE = "C:\\Sentinel_Project\\trades_ledger.csv"
INDEX_PATH = "C:\\Sentinel_Project\\sentinel_episodic.index"
META_PATH = "C:\\Sentinel_Project\\sentinel_meta.json"

def ingest_bitmex():
    print("[BITMEX_INGEST] Initializing Legendary Ingestion Engine...")
    
    # 1. Load BitMEX Trades
    if not os.path.exists(TRADES_FILE):
        print(f"[ERR] File not found: {TRADES_FILE}")
        return
    
    # Load and clean BitMEX data
    df_trades = pd.read_csv(TRADES_FILE)
    df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])
    
    # Filter for executions (Trade/Funding - Funding has PnL)
    # realisedPnl is the target for legendary status
    df_trades = df_trades[df_trades['realisedPnl'].notnull()]
    
    # Isolate top 20% most profitable trades
    threshold = df_trades['realisedPnl'].quantile(0.8)
    legend_trades = df_trades[df_trades['realisedPnl'] >= threshold].copy()
    print(f"[BITMEX_INGEST] Isolated {len(legend_trades)} legendary trades (PnL >= {threshold:.6f} XBt)")

    # 2. Fetch BTC/USD M15 OHLCV from MT5
    if not mt5.initialize():
        print("[ERR] MT5 Init Failed")
        return
        
    print("[BITMEX_INGEST] Fetching historical BTCUSD M15 data for alignment...")
    # Fetch 15,000 bars for now
    rates = mt5.copy_rates_from_pos("BTCUSD", mt5.TIMEFRAME_M15, 0, 15000)
    if rates is None:
        print("[ERR] Failed to fetch rates")
        mt5.shutdown()
        return
    
    df_ohlcv = pd.DataFrame(rates)
    df_ohlcv['time'] = pd.to_datetime(df_ohlcv['time'], unit='s')
    df_ohlcv.set_index('time', inplace=True)
    
    # Ensure timezone awareness
    if df_ohlcv.index.tz is None:
        df_ohlcv.index = df_ohlcv.index.tz_localize('UTC')
    if legend_trades['timestamp'].dt.tz is None:
        legend_trades['timestamp'] = legend_trades['timestamp'].dt.tz_localize('UTC')

    # 3. Align trades to M15 candles (Backward merge)
    legend_trades.sort_values('timestamp', inplace=True)
    merged = pd.merge_asof(
        legend_trades, 
        df_ohlcv, 
        left_on='timestamp', 
        right_index=True, 
        direction='backward'
    )
    
    # Phase 166: Archive Legendary Alignment in ArcticDB
    import sys
    sys.path.append("C:/Users/Administrator/.gemini/antigravity")
    import git_arctic
    try:
        store = git_arctic.get_arctic()
        print("[BITMEX_INGEST] Archiving aligned legendary dataset in ArcticDB...")
        # Write the entire aligned dataframe (can be 173k+ rows)
        store.legend_archive.write("XBTUSD_aligned_legend", merged)
    except Exception as e:
        print(f"[BITMEX_INGEST_ERR] ArcticDB archiving failed: {e}")
    
    # 4. Vectorization & Embedding
    print("[BITMEX_INGEST] Vectorizing legendary execution templates (Dim=93)...")
    memory = EpisodicMemory(dim=93)
    rep_layer = syn.RepresentationLayer()
    
    count = 0
    for idx, row in merged.dropna(subset=['close']).iterrows():
        t = row['timestamp']
        window = df_ohlcv[df_ohlcv.index <= t].tail(128)
        
        if len(window) < 128:
            continue
        
        perception = {
            "symbol": "BTCUSD",
            "ohlcv_df": window,
            "kronos_prob": 0.5,
            "timesfm_p10_dist": 0.0,
            "timesfm_p90_dist": 0.0,
            "hmm_state": "BULL" if row['realisedPnl'] > 0 else "RANGE"
        }
        
        try:
            rep_res = rep_layer.process(perception)
            vector = rep_res['feature_tensor']
            
            memory.store(
                vector=vector,
                action=row['side'],
                pnl=float(row['realisedPnl']),
                reasoning=f"BitMEX Institutional Execution | PnL: {row['realisedPnl']:.6f} XBt",
                lesson="legend_wei"
            )
            count += 1
            if count % 20 == 0:
                print(f" - Embedded {count} templates...")
        except Exception as e:
            print(f"[BITMEX_INGEST] Vectorization error: {e}")
            continue

    print(f"[BITMEX_INGEST] Ingestion Complete. Total Legend Templates: {count}")
    mt5.shutdown()

if __name__ == "__main__":
    ingest_bitmex()
