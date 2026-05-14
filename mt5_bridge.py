import MetaTrader5 as mt5
import logging
import requests
import time
import sys
import os

logger = logging.getLogger("MT5Bridge")

def initialize_mt5_with_heartbeat(watchlist_base):
    """
    v23.6 Directive: Heartbeat Halt & Aggressive Subscription.
    """
    # 1. MT5 Initialize
    if not mt5.initialize():
        logger.error("[BOOT] MT5 Initialization FAILED.")
        return None, []

    # 2. Heartbeat Check (Port 8000 & 8001)
    # v23.6 Rule: Brain must ping Brawn before scanning.
    for port in [8000, 8001]:
        url = f"http://127.0.0.1:{port}/status"
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                logger.info(f"[HEARTBEAT] Port {port} is ONLINE.")
            else:
                logger.critical(f"[HEARTBEAT] Port {port} returned {resp.status_code}. SRE HALT.")
                sys.exit(1)
        except Exception as e:
            logger.critical(f"[HEARTBEAT] Port {port} is OFFLINE: {e}. SRE HALT.")
            sys.exit(1)

    # 3. Aggressive Symbol Subscription & Suffix Resolution
    resolved_watchlist = []
    all_broker_symbols = [s.name for s in mt5.symbols_get()]
    
    logger.info(f"[DISCOVERY] MT5 connected. Scanning broker for {len(watchlist_base)} base symbols...")
    
    for base in watchlist_base:
        # Phase 1: Direct Try + Select
        if mt5.symbol_select(base, True):
            resolved_watchlist.append(base)
            continue
            
        # Phase 2: Suffix Search
        found = False
        for s in all_broker_symbols:
            # Match if it starts with base and has a short suffix
            if s.upper().startswith(base.upper()) and len(s) <= len(base) + 5:
                if mt5.symbol_select(s, True):
                    logger.info(f"[DISCOVERY] Auto-resolved {base} -> {s}")
                    resolved_watchlist.append(s)
                    found = True
                    break
            # Match if base is contained (fallback for weird indices)
            elif base.upper() in s.upper() and len(s) <= len(base) + 10:
                 if mt5.symbol_select(s, True):
                    logger.info(f"[DISCOVERY] Pattern-resolved {base} -> {s}")
                    resolved_watchlist.append(s)
                    found = True
                    break
        
        if not found:
            logger.warning(f"[DISCOVERY] FAILED to resolve or select base: {base}")

    logger.info(f"[DISCOVERY] Final Active Watchlist: {len(resolved_watchlist)}/{len(watchlist_base)} assets.")
    return True, resolved_watchlist
