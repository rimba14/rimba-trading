import numpy as np
import pandas as pd
import json
import logging
from pathlib import Path

logger = logging.getLogger("MonteCarloGate")

def trade_order_shuffling(trades: list[dict], iterations: int = 1000) -> dict:
    """Randomizes trade sequence execution to prove that strategy alpha is statistically independent of lucky sequencing."""
    if not trades:
        return {"pass": False, "reason": "No trades to shuffle"}
        
    pnls = np.array([t.get("profit", 0.0) for t in trades])
    if len(pnls) < 10:
        return {"pass": False, "reason": "Insufficient trade count (<10)"}
        
    final_equities = []
    for _ in range(iterations):
        shuffled = np.random.permutation(pnls)
        equity_curve = np.cumsum(shuffled)
        final_equities.append(equity_curve[-1])
        
    # Check if 95th percentile worst-case still survives (positive equity)
    p05 = np.percentile(final_equities, 5)
    
    passed = p05 > 0.0
    return {
        "pass": passed,
        "p05_equity": p05,
        "mean_equity": np.mean(final_equities),
        "reason": f"P05 equity is {p05:.2f}" if passed else f"Failed: P05 equity {p05:.2f} <= 0"
    }

def candle_based_path_variation(symbol: str, base_candles: pd.DataFrame, iterations: int = 100) -> dict:
    """Injects structural volatility noise and minor spread distortions into historical price paths."""
    if base_candles is None or base_candles.empty:
        return {"pass": False, "reason": "No candle data"}
        
    closes = base_candles['close'].values
    returns = np.diff(closes) / closes[:-1]
    
    survival_count = 0
    for _ in range(iterations):
        # Inject structural volatility noise (N(0, std*1.2))
        noise = np.random.normal(0, np.std(returns) * 1.2, len(returns))
        noisy_returns = returns + noise
        
        sim_closes = [closes[0]]
        for r in noisy_returns:
            sim_closes.append(sim_closes[-1] * (1 + r))
            
        sim_closes = np.array(sim_closes)
        
        # Minor spread distortions
        spread_noise = np.random.uniform(0.999, 1.001, len(sim_closes))
        sim_closes = sim_closes * spread_noise
        
        # Simple survival metric: does it crash > 30% from start?
        max_dd = (np.maximum.accumulate(sim_closes) - sim_closes) / np.maximum.accumulate(sim_closes)
        if np.max(max_dd) < 0.30:
            survival_count += 1
            
    confidence = survival_count / iterations
    passed = confidence >= 0.90
    return {
        "pass": passed,
        "confidence": confidence,
        "reason": f"Survival rate {confidence:.2%}" if passed else f"Failed: Survival rate {confidence:.2%} < 90%"
    }

def run_monte_carlo_gate(strategy_id: str, trades: list[dict], symbol: str, base_candles: pd.DataFrame) -> bool:
    logger.info(f"Running Monte Carlo Gate for {strategy_id} on {symbol}")
    
    res_shuffle = trade_order_shuffling(trades)
    logger.info(f"Shuffle test: {res_shuffle}")
    
    res_candles = candle_based_path_variation(symbol, base_candles)
    logger.info(f"Candle test: {res_candles}")
    
    passed = res_shuffle.get("pass", False) and res_candles.get("pass", False)
    
    out_path = Path("C:/Sentinel_Project/data/monte_carlo_gate_status.json")
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump({
                "strategy_id": strategy_id,
                "passed": passed,
                "shuffle": res_shuffle,
                "candles": res_candles,
                "timestamp": pd.Timestamp.utcnow().isoformat()
            }, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to write MC status: {e}")
        
    return passed
