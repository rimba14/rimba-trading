import os
import sys
import time
import numpy as np
import pandas as pd
import onnxruntime as ort
import logging
import traceback
import torch
import safetensors
from dataclasses import dataclass

# Inject Kronos Repo Path
KRONOS_REPO_PATH = r"C:\Sentinel_Project\kronos_repo"
if KRONOS_REPO_PATH not in sys.path:
    sys.path.append(KRONOS_REPO_PATH)

try:
    from model.kronos import KronosTokenizer
except ImportError as e:
    logging.error(f"[KRONOS_BOOT_ERR] Failed to import KronosTokenizer: {e}")
    KronosTokenizer = None
except Exception as e:
    logging.error(f"[KRONOS_BOOT_ERR] Unexpected error importing KronosTokenizer: {e}")
    KronosTokenizer = None

# Inject project path
sys.path.append(r"C:\Sentinel_Project")
import git_arctic
import gitagent_utils as utils

# Configuration
QUANT_PATH = r"C:\Sentinel_Project\data\kronos_quantized.pt"
CACHE_LIB = "oracle_cache"
TEMPERATURE = 2.5 # Temperature scaling constant to soften conviction

_MODEL = None

def init_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    try:
        # Directive 3: Hard-Lock the Bridge Loader
        if not os.path.exists(QUANT_PATH) or os.path.getsize(QUANT_PATH) < 1000000:
            raise FileNotFoundError(f"Quantized Kronos artifact missing at {QUANT_PATH}")

        print(f"[KRONOS] Loading Pre-Quantized Model from {QUANT_PATH}...")
        _MODEL = torch.load(QUANT_PATH, weights_only=False)
        _MODEL.eval()

        # Directive 3: TurboQuant (v23.3 Omni-Compression)
        # Enable subquadratic attention and memory-efficient KV cache
        if hasattr(_MODEL, 'configure_attention'):
            _MODEL.configure_attention(mode="subquadratic", kv_quantization="4bit")
            print("[KRONOS] Subquadratic Attention & 4-bit KV Cache Enabled.")

        print("[KRONOS] Pre-Quantized Model Loaded Successfully.")
    except Exception as e:
        print(f"[KRONOS] CRITICAL: Model Loading Failed: {e}")
        import traceback
        print(traceback.format_exc())
        raise Exception(f"Failed to load Kronos model: {e}")
    return _MODEL

# Configure Logging
import io as _io
def _get_utf8_stream():
    if getattr(sys.stdout, 'encoding', '').lower() == 'utf-8':
        return sys.stdout
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        return sys.stdout
    except Exception:
        return _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

_UTF8_STREAM = _get_utf8_stream()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [KRONOS_BRIDGE] %(message)s',
                    handlers=[logging.StreamHandler(_UTF8_STREAM)])

def calc_time_stamps(x_timestamp):
    if not pd.api.types.is_datetime64_any_dtype(x_timestamp):
        try:
            x_timestamp = pd.to_datetime(x_timestamp, unit='s')
        except Exception:
            x_timestamp = pd.to_datetime(x_timestamp)
    time_df = pd.DataFrame()
    time_df['minute'] = x_timestamp.dt.minute
    time_df['hour'] = x_timestamp.dt.hour
    time_df['weekday'] = x_timestamp.dt.weekday
    time_df['day'] = x_timestamp.dt.day
    time_df['month'] = x_timestamp.dt.month
    return time_df

@dataclass
class KronosCachePayload:
    """Encapsulates inference metadata for cache commits."""
    prob: float
    xgboost_prob: float = 0.50
    base_atr: float = 0.0
    vol_pct: float = 0.5
    is_bypass: bool = False

class KronosBridge:
    def __init__(self):
        self.model = None
        self.tokenizer_path = "NeoQuasar/Kronos-Tokenizer-base"
        self.tokenizer = None
        self._init_components()
        self.store = git_arctic.get_arctic()

    def _init_components(self):
        try:
            # 1. Init PyTorch Model via Hard-Lock
            self.model = init_model()
            
            # 2. Init Tokenizer
            if KronosTokenizer:
                self.tokenizer = KronosTokenizer.from_pretrained(self.tokenizer_path)
                logging.info("Kronos Tokenizer Loaded.")
            else:
                logging.error("KronosTokenizer class not found.")
        except Exception as e:
            logging.error(f"Bridge Components Init Failed: {e}")
            raise Exception(f"Kronos infer probability error: {e}")

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
                payload = KronosCachePayload(
                    prob=xgboost_prob,
                    xgboost_prob=xgboost_prob,
                    base_atr=base_atr,
                    vol_pct=vol_pct,
                    is_bypass=True
                )
                self.commit_to_cache(symbol, payload)
                return False
            
            logging.info(f"[{symbol}] Wake-Up Gate: ACTIVE (Regime={hmm_state}, XGB={xgboost_prob:.3f})")
            return True
            
        except Exception as e:
            logging.error(f"CRITICAL INFERENCE FAILURE (Gate): {e}")
            logging.error(traceback.format_exc())
            return True # Fallback to active to ensure we don't silently die, but logged loudly

    def commit_to_cache(self, symbol: str, payload: KronosCachePayload):
        """Writes probability to ArcticDB with auxiliary gate data."""
        try:
            # Directive 1: Remove redundant double-stretching. 
            # We now trust the scaling performed in the inference stage.
            scaled_prob = payload.prob

            lib = self.store[CACHE_LIB]
            df_cache = pd.DataFrame([{
                "kronos_prob": float(scaled_prob),
                "xgboost_prob": float(payload.xgboost_prob), # Restore consensus pipeline
                "base_atr": float(payload.base_atr),
                "vol_pct": float(payload.vol_pct),
                "timestamp": utils.get_utc_epoch(),
                "status": "bypassed" if payload.is_bypass else "inferred"
            }])
            
            lib.write(f"{symbol}_kronos", df_cache)
            logging.info(f"[{symbol}] Cache Commit: Kronos={scaled_prob:.3f}, XGB={payload.xgboost_prob:.3f} | ATR={payload.base_atr:.5f} | Vol%={payload.vol_pct:.2f}")
        except Exception as e:
            logging.error(f"Failed to commit cache for {symbol}: {e}")

    def _check_preconditions(self, symbol: str, ohlcv_df: pd.DataFrame) -> bool:
        """Data integrity and wake-up gate verification."""
        if ohlcv_df is None or ohlcv_df.empty or ohlcv_df.isna().any().any():
            logging.warning(f"[{symbol}] Data fetch returned empty or NaN tensor. Aborting inference.")
            return False

        if not self.get_wake_up_gate(symbol):
            return False

        if self.model is None:
            logging.error(f"CRITICAL: Inference requested for {symbol} but Model is OFFLINE.")
            return False

        return True

    def _prepare_inputs(self, df: pd.DataFrame):
        """Prepares OHLCV and Timestamp tensors for the model."""
        price_cols = ['open', 'high', 'low', 'close']
        vol_col = 'tick_volume'
        amt_col = 'real_volume'

        # 1. Map for model input
        x_raw_cols = price_cols + [vol_col, amt_col]
        x_raw = df[x_raw_cols].tail(512).values.astype(np.float32)

        if amt_col in df.columns and (df[amt_col] == 0).all():
            x_raw[:, 5] = x_raw[:, 3] * x_raw[:, 4] # Proxy: close * volume

        if len(x_raw) < 512:
            x_raw = np.pad(x_raw, ((512 - len(x_raw), 0), (0, 0)), mode='edge')

        # 2. Z-Score Normalization
        x_mean = np.mean(x_raw, axis=0)
        x_std = np.std(x_raw, axis=0) + 1e-9
        x_norm = np.clip((x_raw - x_mean) / x_std, -5.0, 5.0)
        x_tensor = torch.from_numpy(x_norm[np.newaxis, :]).float()

        # 3. Tokenization
        if self.tokenizer:
            with torch.no_grad():
                z_indices = self.tokenizer.encode(x_tensor, half=True)
            s1_ids, s2_ids = z_indices[0].long(), z_indices[1].long()
        else:
            s1_ids = torch.zeros((1, 512), dtype=torch.long)
            s2_ids = torch.zeros((1, 512), dtype=torch.long)

        # 4. Timestamps
        time_df = calc_time_stamps(df['time'].tail(512))
        time_df['minute'] /= 59.0
        time_df['hour'] /= 23.0
        time_df['weekday'] /= 6.0
        time_df['day'] /= 31.0
        time_df['month'] /= 12.0

        stamp = time_df.values.astype(np.float32)
        if len(stamp) < 512:
            stamp = np.pad(stamp, ((512 - len(stamp), 0), (0, 0)), mode='edge')
        stamp_tensor = torch.from_numpy(stamp[np.newaxis, :]).float()

        return s1_ids, s2_ids, stamp_tensor, x_mean, x_std

    def _calculate_signal(self, s1_ids, s2_ids, stamp_tensor, x_mean, x_std, ohlcv_df):
        """Executes inference and calculates volatility-adjusted signal."""
        with torch.no_grad():
            outputs = self.model(s1_ids, s2_ids, stamp_tensor)

        s1_logits, s2_logits = outputs[0][:, -1, :], outputs[1][:, -1, :]
        next_s1, next_s2 = torch.argmax(s1_logits, dim=-1, keepdim=True), torch.argmax(s2_logits, dim=-1, keepdim=True)

        base_atr, mu, signal, kronos_raw = 0.0, 0.0, 0.0, 0.5

        if self.tokenizer:
            with torch.no_grad():
                pred_tensor = self.tokenizer.decode([next_s1, next_s2], half=True)
                predicted_close = float(pred_tensor[0, 0, 3])

                # Reverse Z-score
                pred_close_raw = predicted_close * x_std[3] + x_mean[3]
                curr_close_raw = ohlcv_df['close'].iloc[-1]
                mu = (pred_close_raw - curr_close_raw) / (curr_close_raw + 1e-9)

                # ATR (14-period)
                highs, lows, closes = ohlcv_df['high'].tail(100).values, ohlcv_df['low'].tail(100).values, ohlcv_df['close'].tail(100).values
                tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
                base_atr = float(np.mean(tr[-14:]))

                # Scaled Signal
                signal = (pred_close_raw - curr_close_raw) / (base_atr + 1e-9)
                kronos_raw = np.clip(1 / (1 + np.exp(-signal / TEMPERATURE)), 0.01, 0.99)

        return kronos_raw, base_atr, mu, signal

    def _get_aux_metrics(self, symbol: str, ohlcv_df: pd.DataFrame):
        """Retrieves volume percentile and XGBoost baseline."""
        vol_col = 'tick_volume'
        volumes = ohlcv_df[vol_col].tail(512).values
        current_vol = volumes[-1]
        vol_pct = float(np.sum(volumes < current_vol) / len(volumes))

        if vol_pct == 0.0 and current_vol > 0:
            vol_pct = 0.21 # Sanity nudge

        existing_xgb = 0.50
        try:
            lib = self.store[CACHE_LIB]
            if f"{symbol}_kronos" in lib.list_symbols():
                existing_xgb = lib.read(f"{symbol}_kronos").data.iloc[-1].get('xgboost_prob', 0.50)
        except: pass

        return vol_pct, existing_xgb

    def run_inference(self, symbol: str, ohlcv_df: pd.DataFrame):
        """Main execution pipeline (Orchestrator)."""
        if not self._check_preconditions(symbol, ohlcv_df):
            return

        try:
            # Ensure tick_volume exists for metrics (consistent with original logic)
            df = ohlcv_df.copy()
            if 'tick_volume' not in df.columns:
                df['tick_volume'] = 0.0

            # 1. Prepare Inputs
            s1_ids, s2_ids, stamp_tensor, x_mean, x_std = self._prepare_inputs(df)
            
            # 2. Execute Inference & Calculate Signal
            kronos_raw, base_atr, mu, signal = self._calculate_signal(
                s1_ids, s2_ids, stamp_tensor, x_mean, x_std, df
            )
            
            # 3. Auxiliary Metrics
            vol_pct, existing_xgb = self._get_aux_metrics(symbol, df)

            print(f"[SLOW LOOP RAW] {symbol} | Kronos: {kronos_raw:.4f} | Mu: {mu:.6f} | Sig: {signal:.2f} | ATR: {base_atr:.5f} | Vol%: {vol_pct:.2f}")
            payload = KronosCachePayload(
                prob=kronos_raw,
                xgboost_prob=existing_xgb,
                base_atr=base_atr,
                vol_pct=vol_pct,
                is_bypass=False
            )
            self.commit_to_cache(symbol, payload)
            
        except Exception as e:
            logging.error(f"CRITICAL INFERENCE FAILURE: {e}")
            logging.error(traceback.format_exc())

# Singleton instance for legacy bridge support
_BRIDGE = None

def update_cognition_cache(symbol: str, ohlcv_df: pd.DataFrame):
    """Bridge function for sentinel_slow_loop.py"""
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = KronosBridge()
    _BRIDGE.run_inference(symbol, ohlcv_df)

def commit_to_cache(symbol: str, payload: KronosCachePayload):
    """Bridge function for manual cache updates."""
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = KronosBridge()
    _BRIDGE.commit_to_cache(symbol, payload)

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

    # Manual cache commit test
    payload = KronosCachePayload(prob=0.55, xgboost_prob=0.50, base_atr=0.001, vol_pct=0.4)
    commit_to_cache("TEST_ASSET_MANUAL", payload)
