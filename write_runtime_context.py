import json
import os
import time
import MetaTrader5 as mt5

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "runtime_context.json")

def _get_current_session():
    # Placeholder logic for market session
    hour = time.gmtime().tm_hour
    if 1 <= hour < 8:
        return "TOKYO"
    elif 8 <= hour < 13:
        return "LONDON"
    elif 13 <= hour < 21:
        return "NEW_YORK"
    else:
        return "SYDNEY"

def _get_hmm_regime():
    # Placeholder to grab latest regime from gitagent_hmm or cache
    return "RANGE"

def _get_active_directives():
    return ["DIRECTIVE ZETA", "EPISTEMIC_GATE", "AMENDMENT XXV"]

def _calculate_hardware_latency():
    start = time.perf_counter()
    # Simple IO latency test
    try:
        with open("latency_test.tmp", "w") as f:
            f.write("test")
        with open("latency_test.tmp", "r") as f:
            _ = f.read()
        os.remove("latency_test.tmp")
    except:
        pass
    return round((time.perf_counter() - start) * 1000, 2)

def generate_context_snapshot():
    # Ensure config dir exists
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    
    # 1. Open positions
    positions = mt5.positions_get()
    open_tickets = len(positions) if positions else 0
    
    # 2. Drawdown today
    # (Mocked for now, assumes reading from account state)
    account = mt5.account_info()
    drawdown_today = 0.0
    if account:
        drawdown_today = account.balance - account.equity if account.equity < account.balance else 0.0
        
    # 3. Cluster exposure (mocked)
    cluster_exposure = {
        'CRYPTO': 0.15,
        'EQUITY_INDEX': 0.40,
        'FX': 0.45
    }

    context = {
        "session": _get_current_session(),
        "regime": _get_hmm_regime(),
        "open_positions": open_tickets,
        "cluster_exposure": cluster_exposure,
        "drawdown_today": float(round(drawdown_today, 2)),
        "active_directives": _get_active_directives(),
        "hardware_latency_ms": _calculate_hardware_latency(),
        "timestamp": time.time()
    }
    
    with open(CONFIG_PATH, "w") as f:
        json.dump(context, f, indent=4)
        
    return context

if __name__ == "__main__":
    if not mt5.initialize():
        print("MT5 initialization failed")
    else:
        generate_context_snapshot()
        mt5.shutdown()
