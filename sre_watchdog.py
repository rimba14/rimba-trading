import time
import requests
import logging
import sys
import os
import psutil
import MetaTrader5 as mt5
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SRE_WATCHDOG] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(r"C:\sentinel_logs\sre_watchdog.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("SreWatchdog")

EXPECTED_BROKER_OFFSET = 10800 # UTC+3
OFFSET_TOLERANCE = 120 # seconds

def engage_emergency_kill_switch(reason):
    logger.critical(f"[FATAL] ENGAGING SENTINEL EMERGENCY KILL SWITCH: {reason}")
    my_pid = os.getpid()
    purged = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.pid == my_pid:
                continue
            cmd = proc.info.get('cmdline') or []
            cmd_str = " ".join(cmd).lower()
            if any(daemon in cmd_str for daemon in ['sentinel_slow_loop', 'fastapi_sniper', 'profit_manager', 'risk_agent', 'deploy_live']):
                logger.critical(f"[KILL SWITCH] Terminating process {proc.pid}: {proc.name()} ({cmd_str})")
                proc.kill()
                purged += 1
        except Exception as e:
            pass
    logger.critical(f"[FATAL] Purged {purged} trading processes. SRE Watchdog shutting down.")
    sys.exit(1)

def run_temporal_audit():
    logger.info("[AUDIT] Running Temporal Invariant Check...")
    if not mt5.initialize():
        logger.error("[AUDIT] Failed to initialize MT5 for temporal check.")
        return
        
    try:
        tick = mt5.symbol_info_tick("EURUSD")
        if not tick:
            logger.warning("[AUDIT] EURUSD tick not available. Falling back to BTCUSD.")
            tick = mt5.symbol_info_tick("BTCUSD")
            
        if not tick:
            logger.error("[AUDIT] Failed to query broker time from live symbols.")
            return
            
        broker_time = tick.time
        utc_time = time.time()
        current_offset = broker_time - utc_time
        
        logger.info(f"[AUDIT] Broker Time: {datetime.fromtimestamp(broker_time).strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"[AUDIT] UTC Time:    {datetime.fromtimestamp(utc_time).strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"[AUDIT] Offset:      {current_offset:.2f}s (Expected: {EXPECTED_BROKER_OFFSET}s)")
        
        drift = abs(current_offset - EXPECTED_BROKER_OFFSET)
        if drift > 3600:
            logger.warning(f"[STALE TICK] Market is likely closed or booting (Drift: {drift:.2f}s > 3600s). Bypassing drift check.")
        elif drift > OFFSET_TOLERANCE:
            reason = f"[FATAL] Temporal Drift Detected: Current Offset {current_offset:.2f}s differs from expected {EXPECTED_BROKER_OFFSET}s by {drift:.2f}s (tolerance: {OFFSET_TOLERANCE}s)"
            engage_emergency_kill_switch(reason)
        else:
            logger.info(f"[AUDIT] Temporal invariant verified successfully. Drift: {drift:.2f}s.")
    finally:
        mt5.shutdown()

def find_fully_clean_symbol():
    if not mt5.initialize():
        return "EURUSD"
    try:
        from datetime import timedelta
        now = datetime.now()
        lookback = now - timedelta(days=2)
        tomorrow = now + timedelta(days=1)
        
        candidates = [
            "EURCHF", "USDCHF", "GBPCHF", "AUDCAD", "GBPCAD", 
            "AUDNZD", "EURNZD", "GBPNZD", "AUDCHF", "CADCHF", "EURCAD", "USDCAD"
        ]
        
        for sym in candidates:
            deals = mt5.history_deals_get(lookback, tomorrow, group=f"*{sym}*")
            if deals is None or len(deals) == 0:
                return sym
                
        symbols = mt5.symbols_get()
        if symbols:
            for s in symbols:
                deals = mt5.history_deals_get(lookback, tomorrow, group=f"*{s.name}*")
                if deals is None or len(deals) == 0:
                    return s.name
    except Exception:
        pass
    finally:
        mt5.shutdown()
    return "EURUSD"

def run_synthetic_fuzzing():
    logger.info("[FUZZ] Launching Live Synthetic Fuzzing...")
    symbol = find_fully_clean_symbol()
    logger.info(f"[FUZZ] Selected clean fuzzing target symbol: {symbol}")
    
    payload = {
        "symbol": symbol,
        "direction": "BUY",
        "data_quality_flag": "DEGRADED",
        "conviction": 0.99,
        "xgb_p": 0.99,
        "ddqn_p": 0.99,
        "hmm_state": "BULL",
        "signal_type": "MOMENTUM"
    }
    url = "http://localhost:8000/execute_trade"
    headers = {"IS_FUZZING": "True"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=5.0)
        logger.info(f"[FUZZ] POST response code: {resp.status_code}")
        
        if resp.status_code == 200:
            reason = f"[FATAL] Poison Pill Accepted with 200 OK! Gating checks are compromised!"
            engage_emergency_kill_switch(reason)
        elif resp.status_code in [403, 406]:
            logger.info(f"[FUZZ] SUCCESS: Poison Pill correctly rejected with code {resp.status_code}.")
            try:
                detail = resp.json().get("detail", "")
                logger.info(f"[FUZZ] Rejection reason: {detail}")
            except Exception:
                pass
        else:
            logger.warning(f"[FUZZ] Unexpected response code: {resp.status_code}. Response: {resp.text}")
    except requests.exceptions.ConnectionError:
        logger.warning("[FUZZ] Connection Error. FastAPI Sniper is likely offline or restarting. Skipping fuzzing check.")
    except Exception as e:
        logger.error(f"[FUZZ] Fuzzing process error: {e}")

def main():
    logger.info("="*60)
    logger.info("  [BOOT] Sentinel v28.20 SRE Watchdog Daemon Initiated")
    logger.info("="*60)
    
    # Ensure logs folder exists
    os.makedirs(r"C:\sentinel_logs", exist_ok=True)
    
    loop_count = 0
    while True:
        try:
            # 1. Run temporal check every 5 minutes
            run_temporal_audit()
            
            # 2. Run fuzzing check on startup and then every 15 minutes (every 3rd loop)
            if loop_count % 3 == 0:
                run_synthetic_fuzzing()
                
            loop_count += 1
            logger.info(f"[LOOP] Completed iteration {loop_count}. Sleeping 300 seconds...")
            time.sleep(300)
        except KeyboardInterrupt:
            logger.info("[SHUTDOWN] Watchdog received manual interrupt. Exiting gracefully.")
            break
        except Exception as e:
            logger.error(f"[LOOP_ERROR] Error in main loop: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
