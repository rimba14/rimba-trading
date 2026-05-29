import numpy as np
import pandas as pd
import time
import json
import os
from typing import Dict, Any, Tuple
import gitagent_hmm as hmm

# Institutional Constants (Adaptive Sentinel v1.0)
HARD_MULTIPLIERS = {"DEFAULT": 8.0, "XAUUSD": 10.0, "XAGUSD": 12.0, "NAS100": 8.0}
TRAIL_MULTIPLIERS = {
    "EURUSD": {"R0": 4.0, "R1": 6.0},
    "GBPUSD": {"R0": 4.5, "R1": 7.0},
    "XAUUSD": {"R0": 6.0, "R1": 9.0},
    "XAGUSD": {"R0": 8.0, "R1": 12.0},
    "DEFAULT": {"R0": 4.0, "R1": 6.0}
}
STALE_THRESHOLDS = {"XAUUSD": 24, "XAGUSD": 24, "NAS100": 8, "DEFAULT": 48} # Hours

class AdaptiveSentinel:
    def __init__(self, state_file="C:\\Sentinel_Project\\sentinel_risk_state.json"):
        self.state_file = state_file
        self.state = self._load_state()

    def _load_state(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f: return json.load(f)
        return {"peak_equity": 0.0, "regime_history": [], "halt_until": 0}

    def save_state(self):
        with open(self.state_file, 'w') as f: json.dump(self.state, f)

    def calculate_regime(self, df: pd.DataFrame) -> str:
        """Phase 1: Hidden Markov Model Regime Detection"""
        if 'close' not in df.columns or len(df) < 60:
            return "RANGE"
        
        prices = df['close'].values
        label, prob, all_probs = hmm.get_current_state(prices)
        return label

    def calculate_tps(self, hmm_state: str, symbol: str, df: pd.DataFrame, sentiment_score: float) -> float:
        """Step 2: Trade Permission Score (TPS) with HMM Integration"""
        # Base structural signals
        r_sentiment = 1.0 if sentiment_score > 0.5 else (0.5 if sentiment_score >= 0 else 0.0)
        
        hour = time.gmtime().tm_hour
        r_timing = 1.0 if (8 <= hour <= 17) else 0.5 
        
        atr_now = df['high'].sub(df['low']).rolling(14).mean().iloc[-1]
        atr_avg = df['high'].sub(df['low']).rolling(200).mean().iloc[-1]
        r_vol = 1.0 if atr_now <= 1.5 * atr_avg else (0.5 if atr_now <= 2.0 * atr_avg else 0.0)
        
        base_tps = (0.40 * r_sentiment) + (0.30 * r_timing) + (0.30 * r_vol)
        
        # HMM Regime Penalty/Multiplier
        if hmm_state == "RANGE":
            tps = base_tps * 0.5  # 50% penalty for Range/Choppy
        elif hmm_state in ["BULL", "BEAR"]:
            tps = base_tps * 1.2  # 20% boost for trending regimes
        else:
            tps = base_tps
            
        return float(min(1.0, tps))

    def get_kelly_size(self, p: float, equity: float, b: float = 1.5) -> float:
        """
        Step 4: Meta-Labeling Kelly Sizing
        f* = p - (q / b)
        """
        if p <= 0.5: return 0.0
        q = 1.0 - p
        f_raw = p - (q / b)
        
        # Enforce institutional fraction (0.25 Kelly) and 2% Max Risk Cap
        f_kelly = max(0, f_raw) * 0.25
        risk_pct = min(f_kelly, 0.02) 
        
        return equity * risk_pct

    def check_portfolio_heat(self, current_positions: list, equity: float) -> bool:
        """Enforce Total Portfolio Heat Cap (20%)"""
        total_risk = sum(p.get('risk_open', 0.0) for p in current_positions)
        if total_risk >= 0.20 * equity:
            print(f"[BLOCK] Portfolio Heat {total_risk/equity*100:.1f}% >= 20%")
            return False
        return True

    def check_notional_wall(self, volume: float, price: float, equity: float, contract_size: int = 100000) -> bool:
        """Hard Sizing Wall: total_notional / equity <= 10x"""
        notional = volume * price * contract_size
        if (notional / equity) > 10.0:
            print(f"[REJECTED] Notional/Equity Ratio: {notional/equity:.1f}x > 10x")
            return False
        return True

    def get_stop_levels(self, symbol: str, entry_price: float, side: str, atr_entry: float, atr_now: float, hmm_state: str) -> Dict[str, float]:
        """Step 3: 5-Priority Stop Logic (ATR-Sync)"""
        # P1: Hard Stop (Entry ATR)
        mult_hard = 10.0 if symbol == "XAUUSD" else 8.0
        dist_hard = atr_entry * mult_hard
        p1 = entry_price - dist_hard if side == "BUY" else entry_price + dist_hard
        
        # P2: Live Trailing (Current ATR)
        mult_trail = 6.0 if hmm_state in ["BULL", "BEAR"] else 4.0
        dist_trail = atr_now * mult_trail
            
        return {"p1_hard": p1, "p2_dist": dist_trail}

    def audit_circuit_breakers(self, current_equity: float, account_info: dict) -> Tuple[bool, str]:
        """Phase 3: P5 Portfolio Guard with JSON FileLock integration"""
        if time.time() < self.state.get('halt_until', 0):
            return True, "HALTED"

        # Phase 4 Action 1: FileLock integration for circuit_breaker.json
        max_dd = 15.0
        try:
            from filelock import FileLock
            lock = FileLock("C:\\Sentinel_Project\\circuit_breaker.json.lock", timeout=2)
            with lock:
                with open("C:\\Sentinel_Project\\circuit_breaker.json", "r") as f:
                    cb_data = json.load(f)
                    max_dd = float(cb_data.get("max_daily_drawdown_pct", 15.0))
        except Exception as e:
            print(f"[CIRCUIT_BREAKER] Lock/Read failed on circuit_breaker.json: {e}")

        balance = account_info.get('balance', current_equity)
        dd_pct = (balance - current_equity) / (balance + 1e-9) * 100
        
        if dd_pct >= max_dd:
            self.state['halt_until'] = time.time() + (24 * 3600) # 24h halt
            self.save_state()
            return True, "LIQUIDATE_AND_HALT"
        
        if dd_pct >= 8.0:
            return True, "HALVE_POSITIONS"
            
        return False, "NOMINAL"

def get_asset_filters(symbol: str, atr_now: float, trigger_wick: float = 0) -> bool:
    """Phase 3: Specific Asset Blocks"""
    t = time.gmtime()
    hour = t.tm_hour
    dow = t.tm_wday # Mon=0, Fri=4, Sat=5, Sun=6
    
    # 1. Metals (XAU, XAG)
    if symbol.startswith(("XAU", "XAG")):
        # Block Asia (00-08 GMT), 30m pre-NY (12:30-13:00 GMT), Fri 17:00+, Sun open 30m
        if 0 <= hour < 8: return False # Asia
        if hour == 12 and t.tm_min >= 30: return False # pre-NY
        if dow == 4 and hour >= 17: return False # Fri Close
        if dow == 6 and hour == 22 and t.tm_min < 30: return False # Sun Open
        
    # 2. Indices (NAS100, US30)
    if symbol in ["NAS100", "US30", "SPX500"]:
        # Block first 15m NYSE open (14:30 GMT)
        if hour == 14 and t.tm_min < 15: return False
        # Block 30m pre-data (Assuming data at 13:30 or 15:00, use heuristic or manual flag)
        # Skip if wick > 2.5x ATR
        if trigger_wick > 2.5 * atr_now: return False

    return True

def get_position_size(equity: float, stop_points: float, tps: float) -> float:
    """
    Phase 2: Risk-Adjusted Position Sizing
    Calculates lot size based on 2% equity risk cap scaled by TPS.
    """
    if stop_points <= 0: return 0.01
    
    # Max 2% risk, scaled by Trade Permission Score
    risk_pct = min(0.02, tps * 0.02) 
    risk_dollars = equity * risk_pct
    
    # Standard lot size calculation: (Risk / StopDist)
    # Assumes $1.00 per point per lot (standard for major FX and Gold/100)
    lots = risk_dollars / stop_points
    
    # Institutional normalization (Min 0.01, Max 50.0, Step 0.01)
    return float(round(max(0.01, min(50.0, lots)), 2))
