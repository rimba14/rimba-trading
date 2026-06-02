import sys
import json

sys.path.append(r"C:\Sentinel_Project")
try:
    import git_arctic
except ImportError:
    git_arctic = None

from sentinel_config import BASE_WATCHLIST

CRYPTO_SYMBOLS = [
    'BTCUSD', 'ETHUSD', 'SOLUSD', 'AVAXUSD', 'LINKUSD', 
    'LTCUSD', 'BCHUSD', 'XRPUSD', 'ADAUSD', 'DOTUSD', 
    'MATICUSD', 'DOGEUSD', 'UNIUSD', 'ATOMUSD', 'TRXUSD'
]

def extract_crypto():
    ac = None
    if git_arctic:
        try:
            ac = git_arctic.get_arctic()
        except:
            pass

    valid_signals = []
    
    for symbol in CRYPTO_SYMBOLS:
        p_score = 0.0
        cluster = "UNKNOWN"
        atr = 0.001
        
        if ac:
            try:
                meta_item = ac.read(f"{symbol}_meta")
                df_meta = meta_item.data
                
                wass_item = ac.read(f"{symbol}_wasserstein")
                df_wass = wass_item.data
                
                if not df_meta.empty:
                    if 'xgboost_prob' in df_meta.columns:
                        p_score = float(df_meta['xgboost_prob'].iloc[-1])
                    if 'atr' in df_meta.columns:
                        atr = float(df_meta['atr'].iloc[-1])
                        
                if not df_wass.empty and 'state' in df_wass.columns:
                    cluster = str(df_wass['state'].iloc[-1])
            except:
                pass
                
        # Calculate target attributes
        baseline_atr = atr
        lot_size = (baseline_atr / atr) * 0.25 * 0.1
        stop_atr = 4.0
        
        valid_signals.append({
            "Asset": symbol,
            "Conviction_Score": p_score,
            "Thesis": f"Cluster: {cluster}, P: {p_score:.2f} (XGB/Tensor Blend)",
            "Entry": "MARKET",
            "Stop Loss": f"Current +/- {stop_atr} ATR (80% D_guard Frozen)",
            "Take Profit": f"Current -/+ {stop_atr * 1.5} ATR",
            "Sizing": f"{lot_size:.3f} Lot",
            "Warning": "PENDING GATE (0.82 Base)" if p_score < 0.82 else "PRISTINE"
        })
            
    # Sort by P score descending
    valid_signals = sorted(valid_signals, key=lambda x: x['Conviction_Score'], reverse=True)
    
    # Extract top 3
    print("="*40)
    for s in valid_signals[:3]:
        # Remove raw sorting score from final output
        del s['Conviction_Score']
        print(json.dumps(s, indent=2))

if __name__ == "__main__":
    extract_crypto()
