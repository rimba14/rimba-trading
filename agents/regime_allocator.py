import os
import json
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server for Hermes
mcp = FastMCP("Sentinel Regime Allocator")

def evaluate_regime_allocation(symbol: str, hmm_state: str, fft_amplitude_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classifies the market into exactly one of three states based on HMM and TimesNet FFT analysis.
    
    Args:
        symbol: Asset symbol (e.g., BTCUSD).
        hmm_state: The current Hidden Markov Model state ('BULL', 'BEAR', or 'RANGE').
        fft_amplitude_data: Dictionary containing frequency dominance and volatility metrics.
                            Expected keys: 'high_freq_dominance' (bool), 'low_freq_dominance' (bool), 
                            'volatility_sigma' (float), 'anomaly_detected' (bool).
    """
    
    # State 3: HIGH-VOLATILITY (Risk-Off)
    # Condition: fft_amplitude_data exhibits extreme anomalies, broken periodicities, or volatility spikes (> 4.0 Sigma).
    if fft_amplitude_data.get('anomaly_detected') or fft_amplitude_data.get('volatility_sigma', 0) > 4.0:
        return {
            "symbol": symbol,
            "regime": "VOLATILE", 
            "authorized_strategy": "STEP_ASIDE", 
            "momentum_locked": True
        }

    # State 1: RANGE (Mean-Reverting)
    # Condition: hmm_state == 'RANGE'. High-freq dominance is a preference.
    if hmm_state == 'RANGE':
        return {
            "symbol": symbol,
            "regime": "RANGE", 
            "authorized_strategy": "WILLIAMS_WYCKOFF", 
            "momentum_locked": True
        }
    
    # State 2: TREND (Bull/Bear)
    # Condition: hmm_state is BULL or BEAR. Low-freq dominance is a preference.
    if hmm_state in ['BULL', 'BEAR']:
        return {
            "symbol": symbol,
            "regime": "TREND", 
            "authorized_strategy": "KRONOS_MOMENTUM", 
            "momentum_locked": False
        }
    
    # Default fallback (e.g., if data is inconclusive)
    return {
        "symbol": symbol,
        "regime": "UNCERTAIN",
        "authorized_strategy": "STEP_ASIDE",
        "momentum_locked": True
    }

@mcp.tool()
def get_market_regime(symbol: str, hmm_state: str, fft_amplitude_data_json: str) -> str:
    """
    Use this tool before executing any trade to determine if the market regime supports 
    momentum or mean-reversion strategies.
    
    Args:
        symbol: The asset symbol (e.g., 'NAS100').
        hmm_state: The current HMM state ('BULL', 'BEAR', 'RANGE').
        fft_amplitude_data_json: A JSON string containing FFT metrics: 
                                 {"high_freq_dominance": bool, "low_freq_dominance": bool, 
                                  "volatility_sigma": float, "anomaly_detected": bool}
    """
    try:
        fft_data = json.loads(fft_amplitude_data_json)
        result = evaluate_regime_allocation(symbol, hmm_state, fft_data)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

if __name__ == "__main__":
    # Start the MCP server when executed
    mcp.run()
