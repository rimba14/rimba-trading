import pandas as pd
import numpy as np
from arcticdb import Arctic
import gitagent_synthesis as syn
import gitagent_transformer as trans
import torch
import os
from datetime import datetime
import time

# Mock/Import necessary functions from vantage_execute
def rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line - signal_line

import gitagent_microstructure as micro

def calculate_agent_scores_fast(idx, df, trans_model=None):
    """ Fast version of agent scoring using pre-indexed values """
    row = df.iloc[idx]
    price = row['close']
    chg = row['chg']
    sma50 = row['sma50']
    sma200 = row['sma200']
    r = row['rsi']
    macdH = row['macdH']
    vol_ratio = row['vol_ratio']
    
    # Williams
    w_b, w_s = 0.3, 0.1
    if r < 30: w_b+=0.25
    elif r > 70: w_s+=0.2
    if macdH > 0: w_b+=0.15
    else: w_s+=0.1
    tot = w_b + w_s + 0.6
    w_b, w_s = w_b/tot, w_s/tot
    
    # Wyckoff
    wy_b, wy_s = 0.25, 0.15
    if price > sma50 and price > sma200: wy_b+=0.2
    if price < sma50: wy_s+=0.2
    tot = wy_b + wy_s + 0.6
    wy_b, wy_s = wy_b/tot, wy_s/tot
    
    # SMC
    smc_b, smc_s, smc_h = 0.2, 0.1, 0.7
    if price > sma50: smc_b+=0.12 
    if r < 40: smc_b+=0.12 
    if price < sma50: smc_s+=0.12
    tot = smc_b + smc_s + smc_h
    smc_b, smc_s = smc_b/tot, smc_s/tot

    # Transformer (Only run every 5 bars to save time, or use cached)
    trans_score = 0.0
    if trans_model and idx % 2 == 0:
        subset = df.iloc[idx-100:idx][['open', 'high', 'low', 'close', 'tick_volume']].pct_change().fillna(0).values
        src = torch.tensor(subset, dtype=torch.float).unsqueeze(1)
        with torch.no_grad():
            trans_score = float(torch.clamp(trans_model(src), -1.0, 1.0).item())
    
    # Agent 16: Microstructure
    lq_score = micro.get_microstructure_score(df.iloc[max(0, idx-100):idx+1])
    
    features = {
        "W": w_b - w_s,
        "Wy": wy_b - wy_s,
        "SMC": smc_b - smc_s,
        "TRANS": trans_score,
        "RSI": (r - 50) / 50.0,
        "CHG": chg,
        "MICRO": (lq_score - 50) / 50.0
    }
    return features

def prepare_data():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print("MT5 Init Failed")
        return
        
    ac = Arctic("lmdb://C:\\sentinel_arctic")
    if "ppo_training" not in ac.list_libraries():
        ac.create_library("ppo_training")
    lib_ppo = ac.get_library("ppo_training")

    # Pre-load Transformer
    from gitagent_transformer import TransformerEncoderModel
    trans_model = TransformerEncoderModel()
    if os.path.exists("C:\\Sentinel_Project\\transformer_weights.pth"):
        trans_model.load_state_dict(torch.load("C:\\Sentinel_Project\\transformer_weights.pth", map_location='cpu'))
    trans_model.eval()

    for symbol in ["EURUSD", "GBPUSD", "BTCUSD", "USDJPY"]:
        try:
            print(f"Preparing {symbol}...")
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 3000)
            if rates is None or len(rates) < 300: continue
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            
            # Pre-calculate indicators for the entire DF
            df['rsi'] = rsi(df['close'])
            df['macdH'] = macd(df['close'])
            df['sma50'] = df['close'].rolling(50).mean()
            df['sma200'] = df['close'].rolling(200).mean()
            df['chg'] = df['close'].pct_change() * 100
            df['vol_sma'] = df['tick_volume'].rolling(20).mean()
            df['vol_ratio'] = df['tick_volume'] / df['vol_sma']
            
            results = []
            print(f" - Processing {len(df)} bars...")
            for i in range(200, len(df) - 20):
                state = calculate_agent_scores_fast(i, df, trans_model)
                future_ret = (df['close'].iloc[i+10] - df['close'].iloc[i]) / df['close'].iloc[i]
                state['reward'] = future_ret
                state['time'] = df.index[i]
                results.append(state)
            
            if results:
                df_results = pd.DataFrame(results)
                df_results.set_index('time', inplace=True)
                lib_ppo.write(f"{symbol}_STATES", df_results)
                print(f" - {symbol}: Saved {len(df_results)} states.")
        except Exception as e:
            print(f"Error {symbol}: {e}")
    mt5.shutdown()

if __name__ == "__main__":
    prepare_data()
