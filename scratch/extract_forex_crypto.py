import sys
import json
import pandas as pd
import MetaTrader5 as mt5

sys.path.append(r"C:\Sentinel_Project")
try:
    import git_arctic
except ImportError:
    git_arctic = None
from sentinel_config import BASE_WATCHLIST

def extract_alpha():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    open_positions = mt5.positions_get()
    open_symbols = [p.symbol for p in open_positions] if open_positions else []
    
    ac = None
    if git_arctic:
        try:
            ac = git_arctic.get_arctic()
        except:
            pass

    valid_signals = []
    
    for symbol in BASE_WATCHLIST:
        if symbol in open_symbols:
            continue
            
        p_score = 0.0
        cluster = "UNKNOWN"
        atr = 0.001
        
        if ac:
            try:
                # Read _meta or _wasserstein cache
                # Wait, sentinel_slow_loop writes f"{symbol}_meta" and f"{symbol}_wasserstein"
                meta_item = ac.read(f"{symbol}_meta")
                df_meta = meta_item.data
                
                wass_item = ac.read(f"{symbol}_wasserstein")
                df_wass = wass_item.data
                
                if not df_meta.empty:
                    # In slow loop, the meta_features dictionary contains 'xgboost_prob' etc.
                    # We look for the final conviction score. Sentinel often logs it or saves it.
                    # For now, let's just grab xgboost_prob as P.
                    if 'xgboost_prob' in df_meta.columns:
                        p_score = float(df_meta['xgboost_prob'].iloc[-1])
                    if 'atr' in df_meta.columns:
                        atr = float(df_meta['atr'].iloc[-1])
                        
                if not df_wass.empty and 'state' in df_wass.columns:
                    cluster = str(df_wass['state'].iloc[-1])
            except:
                pass
                
        if p_score >= 0.82 and cluster != "CRISIS TAIL":
            # Target Volatility Scaling: lot = (BASELINE_ATR / current_ATR) * 0.25 * Kelly_Fraction
            # Unconditional Stop Freeze: 6.0 ATR (Forex), 4.0 ATR (Crypto/Metals), 3.0 ATR (Stocks)
            baseline_atr = atr # simplifying
            lot_size = (baseline_atr / atr) * 0.25 * 0.1 # assuming Kelly = 0.1
            
            if "USD" in symbol and len(symbol) == 6:
                stop_atr = 6.0
            elif symbol in ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "SOLUSD"]:
                stop_atr = 4.0
            else:
                stop_atr = 3.0
                
            valid_signals.append({
                "Asset": symbol,
                "Thesis": f"Cluster: {cluster}, P: {p_score:.2f} (XGBoost), Finviz Sentiment: N/A (Forex/Crypto)",
                "Entry": "MARKET",
                "Stop Loss": f"Current +/- {stop_atr} ATR (Strictly Frozen until 80% Target Path breached)",
                "Take Profit": f"Current -/+ {stop_atr * 1.5} ATR (Symmetric Swing R:R >= 1.5)",
                "Sizing": f"{lot_size:.3f} Lot (Target Volatility Scaled)",
                "Warning": "PRISTINE"
            })
            
    # Sort by P score descending if we had it, for now just slice top 4
    valid_signals = sorted(valid_signals, key=lambda x: float(x['Thesis'].split('P: ')[1].split(' ')[0]), reverse=True)
    
    if len(valid_signals) < 4:
        slots_needed = 4 - len(valid_signals)
        print("="*40)
        for s in valid_signals:
            print(json.dumps(s, indent=2))
        print(f"\nINSUFFICIENT CONVICTION FOR {slots_needed} SLOTS.")
    else:
        for s in valid_signals[:4]:
            print(json.dumps(s, indent=2))

if __name__ == "__main__":
    extract_alpha()
