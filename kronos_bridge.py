import os
import sys
import time
import numpy as np
import pandas as pd
import onnxruntime as ort
import logging
import traceback
import torch

# Inject Kronos Repo Path
KRONOS_REPO_PATH = r"C:\Sentinel_Project\kronos_repo"
if KRONOS_REPO_PATH not in sys.path:
    sys.path.append(KRONOS_REPO_PATH)

try:
    from model.kronos import KronosTokenizer
except ImportError:
    KronosTokenizer = None

# Inject project path
sys.path.append(r"C:\Sentinel_Project")
import git_arctic
import gitagent_utils as utils

# Configuration
ONNX_PATH = r"C:\Sentinel_Project\kronos_int8.onnx"
CACHE_LIB = "oracle_cache"
TEMPERATURE = 3.0 # Stretch conviction signals

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [KRONOS_BRIDGE] %(message)s')

def calc_time_stamps(x_timestamp):
    time_df = pd.DataFrame()
    time_df['minute'] = x_timestamp.dt.minute
    time_df['hour'] = x_timestamp.dt.hour
    time_df['weekday'] = x_timestamp.dt.weekday
    time_df['day'] = x_timestamp.dt.day
    time_df['month'] = x_timestamp.dt.month
    return time_df

class KronosONNXBridge:
    def __init__(self):
        self.model_path = ONNX_PATH
        self.tokenizer_path = "NeoQuasar/Kronos-Tokenizer-base"
        self.session = None
        self.tokenizer = None
        self._init_session()
        self.store = git_arctic.get_arctic()

    def _init_session(self):
        try:
            # 1. Init ONNX
            if os.path.exists(self.model_path):
                self.session = ort.InferenceSession(self.model_path, providers=['CPUExecutionProvider'])
                logging.info("ONNX Session Ready.")
            else:
                logging.error(f"Model not found at {self.model_path}")
            
            # 2. Init Tokenizer
            if KronosTokenizer:
                self.tokenizer = KronosTokenizer.from_pretrained(self.tokenizer_path)
                logging.info("Kronos Tokenizer Loaded.")
            else:
                logging.error("KronosTokenizer class not found.")
        except Exception as e:
            logging.error(f"Session/Tokenizer Init Failed: {e}")
            return None

    def get_wake_up_gate(self, symbol: str) -> bool:
        """
        The 'Lazy' Wake-Up Gate (Short-Circuit Logic)
        Returns True if inference should proceed, False if bypassed.
        """
        try:
            lib = self.store[CACHE_LIB]
            
            # 1. Check HMM State
            hmm_state = 'RANGE'
            if f"{symbol}_hmm" in lib.list_symbols():
                h_item = lib.read(f"{symbol}_hmm")
                hmm_state = h_item.data.iloc[-1].get('state', 'RANGE')
            
            # 2. Check XGBoost Probability
            if f"{symbol}_kronos" not in lib.list_symbols():
                logging.warning(f"[{symbol}] No XGBoost baseline found in cache. Bypassing gate check.")
                return True
                
            k_item = lib.read(f"{symbol}_kronos")
            xgboost_prob = k_item.data.iloc[-1].get('xgboost_prob')
            
            if xgboost_prob is None:
                logging.warning(f"[{symbol}] XGBoost probability is None. Bypassing gate check.")
                return True
            
            # Directive: Force inference to break the Micro-Variance Squeeze. 
            # The 'Lazy' gate was causing a deadlock where 0.50 signals never escaped the bypass range.
            if False: # (hmm_state == 'RANGE' or (0.45 < xgboost_prob < 0.55)):
                logging.info(f"[{symbol}] Wake-Up Gate: BYPASS (Regime={hmm_state}, XGB={xgboost_prob:.3f})")
                
                # Preserve existing metadata
                base_atr = k_item.data.iloc[-1].get('base_atr', 0.0)
                vol_pct = k_item.data.iloc[-1].get('vol_pct', 0.5)
                
                # Update timestamp to prevent staleness in Fast Loop
                self.commit_to_cache(symbol, xgboost_prob, base_atr=base_atr, vol_pct=vol_pct, is_bypass=True)
                return False
            
            logging.info(f"[{symbol}] Wake-Up Gate: ACTIVE (Regime={hmm_state}, XGB={xgboost_prob:.3f})")
            return True
            
        except Exception as e:
            logging.error(f"CRITICAL INFERENCE FAILURE (Gate): {e}")
            logging.error(traceback.format_exc())
            return True # Fallback to active to ensure we don't silently die, but logged loudly

    def commit_to_cache(self, symbol: str, prob: float, xgboost_prob: float = 0.50, base_atr: float = 0.0, vol_pct: float = 0.5, is_bypass: bool = False):
        """Writes probability to ArcticDB with auxiliary gate data."""
        try:
            # Directive 1: Remove redundant double-stretching. 
            # We now trust the scaling performed in the inference stage.
            scaled_prob = prob

            lib = self.store[CACHE_LIB]
            df_cache = pd.DataFrame([{
                "kronos_prob": float(scaled_prob),
                "xgboost_prob": float(xgboost_prob), # Restore consensus pipeline
                "base_atr": float(base_atr),
                "vol_pct": float(vol_pct),
                "timestamp": utils.get_utc_epoch(),
                "status": "bypassed" if is_bypass else "inferred"
            }])
            
            lib.write(f"{symbol}_kronos", df_cache)
            logging.info(f"[{symbol}] Cache Commit: Kronos={scaled_prob:.3f}, XGB={xgboost_prob:.3f} | ATR={base_atr:.5f} | Vol%={vol_pct:.2f}")
        except Exception as e:
            logging.error(f"Failed to commit cache for {symbol}: {e}")

    def run_inference(self, symbol: str, ohlcv_df: pd.DataFrame):
        """Main execution pipeline."""
        
        # 0. Data Integrity Check
        if ohlcv_df is None or ohlcv_df.empty or ohlcv_df.isna().any().any():
            logging.warning("Data fetch returned empty or NaN tensor. Aborting inference for this tick.")
            return

        # 1. Lazy Wake-Up Gate
        if not self.get_wake_up_gate(symbol):
            return

        # 2. Ensemble Execution (Passed Gate)
        if self.session is None:
            logging.error(f"CRITICAL: Inference requested for {symbol} but ONNX session is OFFLINE.")
            return

        try:
            # 3. Prepare ONNX Inputs
            price_cols = ['open', 'high', 'low', 'close']
            vol_col = 'tick_volume' # MT5 specific
            amt_col = 'real_volume'
            
            df = ohlcv_df.copy()
            if vol_col not in df.columns: df[vol_col] = 0.0
            
            # Map for model input
            x_raw_cols = price_cols + [vol_col, amt_col]
            x_raw = df[x_raw_cols].tail(512).values.astype(np.float32)
            
            # If real_volume is missing or 0, use a proxy for amount
            if amt_col in df.columns and (df[amt_col] == 0).all():
                # amount = close * tick_volume
                x_raw[:, 5] = x_raw[:, 3] * x_raw[:, 4]
            
            if len(x_raw) < 512:
                x_raw = np.pad(x_raw, ((512 - len(x_raw), 0), (0, 0)), mode='edge')
            
            # Directive 2: Robust Z-Score Normalization (Manual)
            x_mean = np.mean(x_raw, axis=0)
            x_std = np.std(x_raw, axis=0) + 1e-9 # Prevent div by zero
            x_norm = (x_raw - x_mean) / x_std
            
            # Clamp outliers to ensure stable gradients
            x_norm = np.clip(x_norm, -3.0, 3.0)
            
            x_tensor = torch.from_numpy(x_norm[np.newaxis, :]).float()
            if self.tokenizer:
                with torch.no_grad():
                    z_indices = self.tokenizer.encode(x_tensor, half=True)
                s1_ids = z_indices[0].numpy().astype(np.int64)
                s2_ids = z_indices[1].numpy().astype(np.int64)
            else:
                s1_ids = np.zeros((1, 512), dtype=np.int64)
                s2_ids = np.zeros((1, 512), dtype=np.int64)
            
            # Directive 2: Normalize Time-Stamps (Prevent 0.50 Collapse)
            time_df = calc_time_stamps(df['time'].tail(512))
            # Scale to [0, 1] range for transformer stability
            time_df['minute'] /= 59.0
            time_df['hour'] /= 23.0
            time_df['weekday'] /= 6.0
            time_df['day'] /= 31.0
            time_df['month'] /= 12.0
            
            stamp = time_df.values.astype(np.float32)
            if len(stamp) < 512:
                stamp = np.pad(stamp, ((512 - len(stamp), 0), (0, 0)), mode='edge')
            stamp = stamp[np.newaxis, :]
            
            # Inference
            outputs = self.session.run(None, {
                's1_ids': s1_ids,
                's2_ids': s2_ids,
                'stamp': stamp
            })
            
            # 4. Extract Meaningful Probability
            # Get logits for the LAST step (prediction for next step)
            s1_logits = torch.from_numpy(outputs[0][:, -1, :])
            s2_logits = torch.from_numpy(outputs[1][:, -1, :])
            
            # Greedy decode next token
            next_s1 = torch.argmax(s1_logits, dim=-1, keepdim=True)
            next_s2 = torch.argmax(s2_logits, dim=-1, keepdim=True)
            
            if self.tokenizer:
                with torch.no_grad():
                    # Decode tokens back to normalized space
                    pred_tensor = self.tokenizer.decode([next_s1, next_s2], half=True)
                    # pred_tensor shape: [1, 1, 6] (OHLCV + extra)
                    predicted_close = float(pred_tensor[0, 0, 3])
                    
                    # Directive 2: Volatility-Adjusted Temperature Scaling
                    # 1. Calculate Predicted Return (mu)
                    # Reverse Z-score to get raw price prediction: price = z * std + mean
                    # x_mean[3] and x_std[3] correspond to 'close' price
                    pred_close_raw = predicted_close * x_std[3] + x_mean[3]
                    curr_close_raw = df['close'].iloc[-1]
                    mu = (pred_close_raw - curr_close_raw) / (curr_close_raw + 1e-9)
                    
                    # 2. Calculate Recent Volatility (ATR)
                    # Use the already calculated base_atr from below (moving it up)
                    highs = df['high'].tail(100).values
                    lows = df['low'].tail(100).values
                    closes = df['close'].tail(100).values
                    tr = np.maximum(highs[1:] - lows[1:], 
                                    np.maximum(np.abs(highs[1:] - closes[:-1]), 
                                               np.abs(lows[1:] - closes[:-1])))
                    base_atr = float(np.mean(tr[-14:]))
                    
                    # 3. Compute Unconstrained Signal (Normalized against ATR)
                    # signal = (Predicted Price Change) / ATR
                    epsilon = 1e-9
                    price_change = pred_close_raw - curr_close_raw
                    signal = price_change / (base_atr + epsilon)
                    
                    # 4. Apply Temperature-Scaled Sigmoid (Phase 2 Rule)
                    # TEMPERATURE = 3.0 multiplier strictly on the Write-Side
                    kronos_raw = 1 / (1 + np.exp(-signal * TEMPERATURE))
                    
                    # Clamp output to [0.01, 0.99] to maintain resolution
                    kronos_raw = np.clip(kronos_raw, 0.01, 0.99)
            else:
                kronos_raw = 0.5
                mu = 0.0
                signal = 0.0

            # ATR already calculated above as base_atr
            # (Redundant block removed)
            
            volumes = df[vol_col].tail(512).values
            current_vol = volumes[-1]
            vol_pct = float(np.sum(volumes < current_vol) / len(volumes))
            
            # Sanity nudge: ensure we don't block just because of exactly zero volume history 
            # if the current volume is at least 1.
            if vol_pct == 0.0 and current_vol > 0:
                vol_pct = 0.21 

            # Retrieve existing XGBoost probability to preserve consensus pipeline
            existing_xgb = 0.50
            try:
                lib = self.store[CACHE_LIB]
                if f"{symbol}_kronos" in lib.list_symbols():
                    k_item = lib.read(f"{symbol}_kronos")
                    existing_xgb = k_item.data.iloc[-1].get('xgboost_prob', 0.50)
            except: pass

            print(f"[SLOW LOOP RAW] {symbol} | Kronos: {kronos_raw:.4f} | Mu: {mu:.6f} | Sig: {signal:.2f} | ATR: {base_atr:.5f} | Vol%: {vol_pct:.2f}")
            
            self.commit_to_cache(symbol, kronos_raw, xgboost_prob=existing_xgb, base_atr=base_atr, vol_pct=vol_pct, is_bypass=False)
            
        except Exception as e:
            logging.error(f"CRITICAL INFERENCE FAILURE: {e}")
            logging.error(traceback.format_exc())

# Singleton instance for legacy bridge support
_BRIDGE = None

def update_cognition_cache(symbol: str, ohlcv_df: pd.DataFrame):
    """Bridge function for sentinel_slow_loop.py"""
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = KronosONNXBridge()
    _BRIDGE.run_inference(symbol, ohlcv_df)

if __name__ == "__main__":
    # Test with realistic mock data
    n = 600
    mock_df = pd.DataFrame({
        'time': pd.date_range(start='2023-01-01', periods=n, freq='15min'),
        'open': np.random.randn(n) + 100,
        'high': np.random.randn(n) + 101,
        'low': np.random.randn(n) + 99,
        'close': np.random.randn(n) + 100,
        'tick_volume': np.random.randint(100, 1000, n),
        'real_volume': np.random.randint(100, 1000, n)
    })
    update_cognition_cache("TEST_ASSET", mock_df)
