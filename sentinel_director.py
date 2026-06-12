import os
import sys
import time
import json
import asyncio
import numpy as np

# Add paths to make sure we can import sentinel modules
sys.path.append(r"C:\Users\ADMIN\.antigravity\rimba-trading")
sys.path.append(r"C:\Sentinel_Project")

import sentinel_config as cfg

STATE_DIR = r"C:\Sentinel_Project\data"
if not os.path.exists(STATE_DIR):
    STATE_DIR = r"C:\Users\ADMIN\.antigravity\rimba-trading\data"
os.makedirs(STATE_DIR, exist_ok=True)

CONSENSUS_FILE = os.path.join(STATE_DIR, "consensus_state.json")

def load_json_state(name):
    path = os.path.join(STATE_DIR, f"{name}_state.json")
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def trigger_graceful_degradation(reason):
    """Enforces absolute safety by halting all entries and logging status."""
    print(f"[DEGRADATION_TRIGGERED] {reason}. Freezing entries, scaling risk to 0.0.")
    # Write empty consensus signals to freeze entries
    consensus_payload = {
        "timestamp": int(time.time()),
        "status": "GRACEFUL_DEGRADATION",
        "reason": reason,
        "signals": {symbol: "HOLD" for symbol in cfg.WATCHLIST}
    }
    temp_file = CONSENSUS_FILE + ".tmp"
    with open(temp_file, "w") as f:
        json.dump(consensus_payload, f, indent=2)
    os.replace(temp_file, CONSENSUS_FILE)
    
    # Save 0.0 size multiplier to risk configuration to scale down token/leverage footprint
    try:
        risk_params_path = "dynamic_risk_params.json"
        config = {}
        if os.path.exists(risk_params_path):
            with open(risk_params_path, "r") as f:
                config = json.load(f)
        config["health_size_multiplier"] = 0.0
        config["graceful_degradation_active"] = True
        with open(risk_params_path, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"[DEGRADATION_ERR] Failed to modify risk config: {e}")

async def run_perception_workers():
    """Spins up isolated subprocesses for perception micro-workers."""
    print("[DIRECTOR] Dispatching isolated perception workers...")
    
    # Use sys.executable to run workers in parallel
    proc_t = await asyncio.create_subprocess_exec(sys.executable, "indicator_timesnet.py")
    proc_m = await asyncio.create_subprocess_exec(sys.executable, "indicator_mixts.py")
    proc_h = await asyncio.create_subprocess_exec(sys.executable, "indicator_hmm.py")
    
    # Run trailing stop-loss worker concurrently
    proc_c = await asyncio.create_subprocess_exec(sys.executable, "cades_sentinel.py")
    
    await asyncio.gather(
        proc_t.wait(),
        proc_m.wait(),
        proc_h.wait(),
        proc_c.wait()
    )
    print("[DIRECTOR] Perception and exit workers finished execution.")

async def verify_and_consensus():
    """Executes the Sandwich Underwriter Gate consensus verification across JSON state files."""
    tnet_states = load_json_state("timesnet")
    mixts_states = load_json_state("mixts")
    hmm_states = load_json_state("hmm")
    
    signals = {}
    
    for symbol in cfg.WATCHLIST:
        tnet_data = tnet_states.get(symbol)
        mixts_data = mixts_states.get(symbol)
        hmm_data = hmm_states.get(symbol)
        
        # 1. Underwriter Gate: Check if all workers have written state for this symbol
        if not tnet_data or not mixts_data or not hmm_data:
            print(f"[GATE_ALERT] Data starvation for {symbol}. Skipping.")
            signals[symbol] = "HOLD"
            continue
            
        # 2. Underwriter Gate: Check for signal staleness
        now = time.time()
        if (now - tnet_data["timestamp"] > 300 or 
            now - mixts_data["timestamp"] > 300 or 
            now - hmm_data["timestamp"] > 300):
            print(f"[GATE_ALERT] Stale worker states for {symbol}. Skipping.")
            signals[symbol] = "HOLD"
            continue
            
        # 3. Underwriter Gate: Check epistemic status and Wasserstein bounds
        if not tnet_data["epistemic_pass"] or not mixts_data["epistemic_pass"] or not hmm_data["epistemic_pass"]:
            print(f"[GATE_ALERT] Epistemic failure or anomaly detected for {symbol}. Rejecting entries.")
            signals[symbol] = "HOLD"
            continue
            
        if (tnet_data["wasserstein_distance"] > 0.65 or 
            mixts_data["wasserstein_distance"] > 0.65 or 
            hmm_data["wasserstein_distance"] > 0.65):
            print(f"[GATE_ALERT] Wasserstein distance breach on {symbol}. Rejecting entries.")
            signals[symbol] = "HOLD"
            continue
            
        # 4. Consensus Vector computation
        tnet_conf = tnet_data["confidence_vector"]
        mixts_conf = mixts_data["confidence_vector"]
        hmm_conf = hmm_data["confidence_vector"]
        
        # Weighted probability model (0.3 TimesNet, 0.4 MixTS, 0.3 HMM)
        bull_score = tnet_conf[0] * 0.3 + mixts_conf[0] * 0.4 + hmm_conf[0] * 0.3
        
        if bull_score > 0.68:
            signals[symbol] = "BUY"
        elif bull_score < 0.32:
            signals[symbol] = "SELL"
        else:
            signals[symbol] = "HOLD"
            
    # Output final consensus state to disk
    consensus_payload = {
        "timestamp": int(time.time()),
        "status": "NORMAL",
        "signals": signals
    }
    
    temp_file = CONSENSUS_FILE + ".tmp"
    with open(temp_file, "w") as f:
        json.dump(consensus_payload, f, indent=2)
    os.replace(temp_file, CONSENSUS_FILE)
    print(f"[DIRECTOR] Wrote consensus signals to disk for {len(signals)} assets.")

async def main():
    print("[DIRECTOR] Starting Sentinel Central Director Orchestrator loop...")
    
    # Command line argument support for dry-runs
    if "--test-dry-run" in sys.argv:
        print("[DIRECTOR] Running dry-run validation step...")
        await run_perception_workers()
        await verify_and_consensus()
        print("[DIRECTOR] Dry-run completed successfully.")
        return

    while True:
        try:
            # 1. Run subprocesses for all perception/trailing modules
            await run_perception_workers()
            
            # 2. Run verification & consensus subject to the 50ms strict sync cap
            t0 = time.perf_counter()
            try:
                await asyncio.wait_for(verify_and_consensus(), timeout=0.050)
                duration_ms = (time.perf_counter() - t0) * 1000.0
                print(f"[DIRECTOR] Consensus calculation completed in {duration_ms:.2f}ms (50ms cap).")
            except asyncio.TimeoutError:
                trigger_graceful_degradation("Consensus loop synchronization cap exceeded 50ms")
                
        except Exception as e:
            print(f"[DIRECTOR_CRITICAL_ERR] {e}")
            trigger_graceful_degradation(f"Director critical exception: {e}")
            
        # Loop interval aligned to M15 bar (e.g. run every 300 seconds)
        await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())
