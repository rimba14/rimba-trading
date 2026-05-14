import sys
sys.path.append("C:/Sentinel_Project")
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone
import feature_engineering as feat_eng

def get_ticks_at(symbol, target_ts):
    dt = datetime.fromtimestamp(target_ts, tz=timezone.utc)
    # Get ticks for the 15 minutes preceding the target timestamp to get enough rows
    from_dt = datetime.fromtimestamp(target_ts - 900, tz=timezone.utc)
    
    ticks = mt5.copy_ticks_range(symbol, from_dt, dt, mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) == 0:
        print(f"No ticks found for {symbol} ending at {dt}")
        return None
    
    df = pd.DataFrame(ticks)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    if 'real_volume' not in df.columns:
        df['real_volume'] = df['volume'] if 'volume' in df.columns else 0.0
    if 'tick_volume' not in df.columns:
        df['tick_volume'] = df['real_volume']
    if 'volume' not in df.columns:
        df['volume'] = df['real_volume']
        
    p_series = df['last'].where(df['last'] > 0, df['bid'])
    df['close'] = p_series
    df['open']  = p_series
    df['high']  = p_series
    df['low']   = p_series
    
    return df

def run_reconstruction():
    if not mt5.initialize():
        print("MT5 init failed")
        return
        
    targets = [
        ("NAS100", 1778579282), # 2026-05-12 09:48:02 UTC
        ("US2000", 1778530870)  # 2026-05-11 20:21:10 UTC
    ]
    
    for sym, ts in targets:
        print(f"\n================ Reconstructing {sym} at entry TS {ts} ================")
        df = get_ticks_at(sym, ts)
        if df is not None:
            print(f"Retrieved {len(df)} ticks ending at {df['time'].iloc[-1]}")
            vol_col = "tick_volume" if "tick_volume" in df.columns else "volume"
            df_feat = feat_eng.engineer_features(df, price_col="close", volume_col=vol_col)
            last_row = df_feat.iloc[-1]
            print(f"Hawkes Intensity:   {last_row.get('hawkes_intensity', 0.0):.6f}")
            print(f"Order-Flow Entropy: {last_row.get('order_flow_entropy', 0.0):.6f}")
            print(f"VPIN:               {last_row.get('vpin', 0.0):.6f}")
    
    mt5.shutdown()

if __name__ == "__main__":
    run_reconstruction()
