import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import os
import json
import re
from datetime import datetime, timedelta, timezone

def analyze_trade_history(deals):
    if not deals:
        return {}
    
    df = pd.DataFrame([d._asdict() for d in deals])
    # Filter for closing trades with profit != 0 (or at least OUT deals)
    df_out = df[df['entry'] == 1] # mt5.DEAL_ENTRY_OUT == 1
    
    if df_out.empty:
        return {}
        
    wins = df_out[df_out['profit'] > 0]
    losses = df_out[df_out['profit'] <= 0]
    
    gross_profit = wins['profit'].sum()
    gross_loss = abs(losses['profit'].sum())
    
    win_rate = len(wins) / len(df_out) if len(df_out) > 0 else 0
    avg_win = wins['profit'].mean() if not wins.empty else 0
    avg_loss = losses['profit'].mean() if not losses.empty else 0
    
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    return {
        'total_trades': len(df_out),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss
    }

def audit_exit_mechanisms(log_path):
    if not os.path.exists(log_path):
        return {}
        
    stats = {
        'HARD VIRTUAL STOP': 0,
        'THESIS DECAY': 0,
        'TIME STOP': 0,
        'MUTUAL EXCLUSION': 0,
        'THESIS COMPLETE / VTP': 0,
        'TOTAL_LIQUIDATIONS': 0
    }
    
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if '[AUTONOMOUS SRE]' in line or 'REGIME_VIOLATION_LIQUIDATION' in line or 'Mutual Exclusion' in line:
                if '[HARD VIRTUAL STOP]' in line:
                    stats['HARD VIRTUAL STOP'] += 1
                elif '[TIME STOP / THESIS DECAY]' in line:
                    stats['TIME STOP'] += 1
                elif '[THESIS DECAY]' in line: # Fallback for old logs
                    stats['THESIS DECAY'] += 1
                elif 'Mutual Exclusion' in line:
                    stats['MUTUAL EXCLUSION'] += 1
                elif '[THESIS COMPLETE / VTP]' in line:
                    stats['THESIS COMPLETE / VTP'] += 1
                else:
                    # Generic regime violation count as thesis decay
                    if 'REGIME_VIOLATION_LIQUIDATION' in line and '[AUTONOMOUS SRE]' not in line:
                        pass # avoid double counting if they are logged twice
    
    # Check MT5 history comments for Mutual Exclusion
    return stats

def run_diagnostics():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return
        
    now = datetime.now()
    from_date = now - timedelta(days=7) # analyze last 7 days
    deals = mt5.history_deals_get(from_date, now)
    
    print("--- DIRECTIVE 1: TRADE HISTORY & PNL DISTRIBUTION ---")
    d1_stats = analyze_trade_history(deals)
    print(json.dumps(d1_stats, indent=2))
    
    print("\n--- DIRECTIVE 2: EXIT MECHANISM AUDIT ---")
    log_path = r"C:\sentinel_logs\profit_manager_v19_2.log"
    d2_stats = audit_exit_mechanisms(log_path)
    # Check history deals for Mutual Exclusion
    if deals:
        df = pd.DataFrame([d._asdict() for d in deals])
        mut_ex = len(df[df['comment'].str.contains('Mutual Excl', na=False)])
        d2_stats['MUTUAL EXCLUSION'] += mut_ex
        
    total_tracked = sum(d2_stats.values()) - d2_stats.get('TOTAL_LIQUIDATIONS', 0)
    d2_stats['TOTAL_TRACKED'] = total_tracked
    for k, v in d2_stats.items():
        if k not in ['TOTAL_LIQUIDATIONS', 'TOTAL_TRACKED']:
            pct = (v / total_tracked * 100) if total_tracked > 0 else 0
            print(f"{k}: {v} ({pct:.1f}%)")
            
    print("\n--- DIRECTIVE 4: HMM REGIME MISCLASSIFICATION ---")
    # Extract regime from order comments or match timestamps
    if deals:
        df = pd.DataFrame([d._asdict() for d in deals])
        df_in = df[df['entry'] == 0] # mt5.DEAL_ENTRY_IN
        # Try to find regime in json files in cognition_queue or pending_diagnostics
        diag_dir = r"C:\Sentinel_Project\pending_diagnostics"
        print(f"Scanning diagnostics in {diag_dir} to correlate losses with regimes...")
        regime_losses = {'BULL': 0.0, 'BEAR': 0.0, 'RANGE': 0.0}
        regime_wins = {'BULL': 0.0, 'BEAR': 0.0, 'RANGE': 0.0}
        
        if os.path.exists(diag_dir):
            for f in os.listdir(diag_dir):
                if 'regime_liq' in f:
                    try:
                        with open(os.path.join(diag_dir, f), 'r') as fp:
                            data = json.load(fp)
                            regime = data.get('hmm_state', 'UNKNOWN')
                            pnl = data.get('pnl', 0)
                            if regime in regime_losses:
                                if pnl < 0:
                                    regime_losses[regime] += abs(pnl)
                                else:
                                    regime_wins[regime] += pnl
                    except:
                        pass
        print(f"Losses by Entry/Exit Regime (approximated from SRE drops):")
        print(f"BULL: {regime_losses['BULL']:.2f}")
        print(f"BEAR: {regime_losses['BEAR']:.2f}")
        print(f"RANGE: {regime_losses['RANGE']:.2f}")
        
    mt5.shutdown()

if __name__ == "__main__":
    run_diagnostics()
