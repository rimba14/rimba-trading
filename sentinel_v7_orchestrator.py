import os
import time
import json
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
import git_arctic
import gitagent_hmm as hmm
import gitagent_memory as memory
import gitagent_action_layer as action_layer
import gitagent_timesfm_adapter as timesfm
import medallion_sizing as sizing
import gitagent_utils as utils

# -----------------------------------------------------------------------------
# PHASE 1: LOOP SYNCHRONIZATION & INFRASTRUCTURE CHECK
# -----------------------------------------------------------------------------
def initialize_sentinel_v7():
    print("--- Phase 1: Loop Synchronization & Infrastructure Check ---")
    
    # Verify ArcticDB Connection
    try:
        ac = git_arctic.get_arctic()
        libs = ac.list_libraries()
        print(f"[OK] ArcticDB Connected. Libraries: {libs}")
        
        if "oracle_cache" not in libs:
            ac.create_library("oracle_cache")
            print("[INFO] Created missing oracle_cache library")
        if "legend_archive" not in libs:
            ac.create_library("legend_archive")
            print("[INFO] Created missing legend_archive library")
            
        oracle_cache = ac["oracle_cache"]
        legend_archive = ac["legend_archive"]
    except Exception as e:
        print(f"[ERROR] ArcticDB Latency Spike or Connection Failure: {e}")
        print("[HALT] Defaulting to legacy ATR defense.")
        return None, None, None

    # Verify MT5
    if not mt5.initialize():
        print("[ERROR] MT5 Initialization Failed.")
        return None, None, None
        
    print("[OK] Infrastructure Verified.\n")
    return ac, oracle_cache, legend_archive

# -----------------------------------------------------------------------------
# PHASE 2: PERCEPTION & COGNITION (THE ORACLES)
# -----------------------------------------------------------------------------
def get_cognition_v7(symbol, oracle_cache, ohlcv_df):
    print("--- Phase 2: Perception & Cognition ---")
    
    # 1. HMM Oracle
    prices = ohlcv_df['close'].values
    hmm_state, hmm_prob, _ = hmm.get_current_state(prices)
    
    # HMM Penalty Logic: BULL/BEAR multiplier 1.2, RANGE penalty 0.5
    tps_multiplier = 1.0
    if hmm_state in ["BULL", "BEAR"]:
        tps_multiplier = 1.2
    elif hmm_state == "RANGE":
        tps_multiplier = 0.5
    
    print(f"[HMM] State: {hmm_state} | Prob: {hmm_prob:.2f} | Multiplier: {tps_multiplier}")

    # 2. Kronos Oracle (from ArcticDB)
    p_kronos = 0.50 
    try:
        # Check if symbol exists in cache
        if f"{symbol}_kronos" in oracle_cache.list_symbols():
            cache_data = oracle_cache.read(f"{symbol}_kronos").data
            if not cache_data.empty:
                # check for staleness (15 mins)
                last_ts = cache_data.iloc[-1].get('timestamp', 0)
                if time.time() - last_ts < 900:
                    p_kronos = float(cache_data.iloc[-1]['p_kronos'])
                    print(f"[KRONOS] Retrieved cached probability: {p_kronos:.3f}")
                else:
                    print("[KRONOS] Cache is STALE (> 15 mins). Defaulting to 0.50")
    except Exception as e:
        print(f"[ERROR] Kronos Cache Read Error: {e}")
        
    return hmm_state, tps_multiplier, p_kronos

# -----------------------------------------------------------------------------
# PHASE 3: CONTEXTUAL MEMORY AUDIT
# -----------------------------------------------------------------------------
def memory_audit_v7(symbol, live_vector, legend_archive):
    print("--- Phase 3: Contextual Memory Audit ---")
    mem = memory.EpisodicMemory(dim=93) # FAISS 93-dim
    
    top_matches = mem.retrieve(live_vector, k=3)
    
    legend_boost = 1.0
    is_legend = False
    
    for match in top_matches:
        # Distance to Similarity (approximate)
        similarity = 1.0 / (1.0 + match['distance']) 
        if similarity > 0.85:
            print(f"[LEGEND] Match Detected! Similarity: {similarity:.2f} to {match['meta'].get('reasoning', 'Unknown Episode')}")
            legend_boost = 1.3 # 30% TPS boost
            is_legend = True
            break
            
    if not is_legend:
        print("[MEMORY] No legend matches detected above 85%.")
        
    return legend_boost, is_legend

# -----------------------------------------------------------------------------
# PHASE 5 Execution Helper (to wrap ActionLayer)
# -----------------------------------------------------------------------------
def execute_v7_workflow(symbol, side, p_blended, hcs_base, legend_boost, is_legend, atr_now, current_price, account_info):
    print("--- Phases 4 & 5: Risk Gates & Execution ---")
    
    # 1. TPS Calculation
    tps = min(1.0, (hcs_base / 4.0) * legend_boost)
    print(f"[TPS] Base HCS: {hcs_base}/4 | Boost: {legend_boost}x | Final TPS: {tps:.2f}")

    # 2. Risk Gates & Sizing (using medallion_sizing)
    # We need to simulate current positions for the heat check
    positions = mt5.positions_get()
    current_pos_list = []
    if positions:
        for p in positions:
            info = mt5.symbol_info(p.symbol)
            contract_size = info.trade_contract_size if info else 100000
            current_pos_list.append({
                'symbol': p.symbol,
                'risk_dollars': 0.0, # This should ideally be calculated/stored
                'notional_value': p.volume * p.price_open * contract_size
            })
    
    allowed, reason = sizing.check_portfolio_gates(symbol, current_pos_list, account_info.equity)
    
    # Legend Override: Override visual/lagging rejections
    if not allowed and is_legend:
        print(f"[LEGEND_OVERRIDE] Overriding Gate Rejection: {reason}")
        allowed = True
    
    if not allowed:
        print(f"[BLOCK] Portfolio Gate Rejection: {reason}")
        return False

    # 3. Size calculation
    # p_blended is used for Kelly
    size_data = sizing.get_medallion_size(symbol, {'equity': account_info.equity}, atr_now, hcs_base, kronos_prob=p_blended)
    risk_dollars = size_data['calculated_risk_dollars']
    
    if risk_dollars <= 0:
        print("[STATUS] No mathematical edge (Kelly f* <= 0). No trade.")
        return False

    # Calculate total volume based on risk and ATR
    # Simplified lot calculation: (Risk / (ATR * Multiplier))
    # Using 8x ATR for hard stop as per v1.0
    info = mt5.symbol_info(symbol)
    contract_size = info.trade_contract_size if info else 100000
    stop_dist = atr_now * 8.0
    total_volume = risk_dollars / (stop_dist * contract_size)
    total_volume = round(max(0.01, min(50.0, total_volume)), 2)

    print(f"[SIZING] Risk: ${risk_dollars:.2f} | Total Volume: {total_volume} lots")

    # 4. Action Layer Execution (Phases 5)
    al = action_layer.get_action_layer()
    orders = al.execute_smart_trade(symbol, side, total_volume, current_price, atr_now, tps, account_info.equity)
    
    if orders:
        print(f"[SUCCESS] {len(orders)} sub-orders placed.")
        return True
    return False

def run_v7_audit():
    symbol = "XAUUSD"
    print(f"=== Adaptive Sentinel Execution & Risk Audit (v7.0) - {symbol} ===")
    
    # Phase 1
    ac, oracle_cache, legend_archive = initialize_sentinel_v7()
    if not ac: return

    # Fetch Data
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 500)
    if rates is None:
        print("[ERROR] Failed to fetch MT5 rates.")
        return
    df = pd.DataFrame(rates)
    
    # Phase 2
    hmm_state, hmm_mult, p_kronos = get_cognition_v7(symbol, oracle_cache, df)
    
    # Phase 3
    # Construct a dummy 93-dim vector for the demo
    dummy_vec = np.random.randn(93).astype('float32') 
    legend_boost, is_legend = memory_audit_v7(symbol, dummy_vec, legend_archive)
    
    # Phase 4 & 5
    acc = mt5.account_info()
    if acc is None: return

    current_price = df['close'].iloc[-1]
    atr_now = df['high'].sub(df['low']).rolling(14).mean().iloc[-1]
    
    # Calculate base HCS
    hcs_base = sizing.calculate_hcs(df, sentiment_score=0.3) # Dummy sentiment
    
    # Execution
    side = "BUY" if hmm_state == "BULL" else ("SELL" if hmm_state == "BEAR" else "BUY")
    
    success = execute_v7_workflow(symbol, side, p_kronos, hcs_base, legend_boost, is_legend, atr_now, current_price, acc)

    print("\n" + "="*50)
    print(f"TERMINAL STATUS (v7.0):")
    print(f"HMM State: {hmm_state}")
    print(f"Portfolio Heat: {sizing.MAX_ACCOUNT_RISK_CAP*100:.1f}% Limit")
    print(f"Sub-Order Status: {'EXECUTED' if success else 'BLOCKED/SKIPPED'}")
    print(f"TimesFM Integrity: {'VERIFIED (P10/P90 ACTIVE)' if timesfm.TimesFM_2p5_200M_torch else 'FALLBACK ACTIVE'}")
    print(f"Memory Match: {'LEGEND_DETECTION_ACTIVE' if is_legend else 'SCAN_COMPLETE'}")
    print("="*50)

    mt5.shutdown()

if __name__ == "__main__":
    run_v7_audit()
