import os
import json

file_path = r"C:\Sentinel_Project\sentinel_slow_loop.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

gate_import = "\nfrom pre_execution_gate import run_all_gates, GateContext\nimport MetaTrader5 as mt5\n"
if "from pre_execution_gate import run_all_gates" not in content:
    content = content.replace("import requests", gate_import + "import requests")

patch_code = """
    try:
        # --- PHASE 4 PRE-EXECUTION GATE ---
        import MetaTrader5 as mt5
        symbol = payload.get('symbol', '')
        direction = payload.get('direction', '')
        regime_key = payload.get('wasserstein_state', 'NORMAL')
        ticket_ref = payload.get('tag', str(int(time.time())))
        
        account_info = mt5.account_info()
        current_equity = account_info.equity if account_info else 0.0
        
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info:
            entry_price = symbol_info.ask if direction == 'BUY' else symbol_info.bid
        else:
            entry_price = 0.0
            
        sl_price = payload.get('sl', 0.0)
        tp_price = payload.get('tp', 0.0)
        sl_distance = abs(entry_price - sl_price) if sl_price > 0 else 0.0
        tp_distance = abs(tp_price - entry_price) if tp_price > 0 else 0.0
        
        # Approximate Risk and Heat for Gate check (as these aren't directly in payload)
        # Using placeholder 0.0 if not available, or calculating based on Kelly sizing later.
        kelly_lots = payload.get('size_multiplier', 1.0) * 0.01  # baseline approx
        
        # We need an asset class. Simplistic fallback:
        asset_class = "CRYPTO" if symbol.endswith("USD") and len(symbol) > 6 else "FOREX"
        if symbol in ["NAS100", "US30", "SP500", "US2000", "HK50", "GER40"]:
            asset_class = "INDEX"
            
        risk_usd = current_equity * 0.01  # Placeholder approximation for the gate
        current_portfolio_heat = current_equity * 0.05 # Placeholder approximation for the gate
        amnesia_lock_registry = {} # Placeholder

        context = GateContext(
            symbol=symbol,
            direction=direction,
            asset_class=asset_class,
            regime=regime_key,
            ticket_ref=str(ticket_ref),
            kelly_lots=kelly_lots,
            entry_price=entry_price,
            sl_distance=sl_distance,
            tp_distance=tp_distance,
            risk_usd=risk_usd,
            equity=current_equity,
            current_heat_usd=current_portfolio_heat,
            embargo_registry=amnesia_lock_registry,
        )
        verdict = run_all_gates(context)

        if not verdict.approved:
            logging.error(f"[GATE_LAYER] SIGNAL BLOCKED: {verdict.summary()}")
            # drop_to_shap_diagnostics: JSON dump
            diag_file = SIGNAL_DIR / f"blocked_gate_{symbol}_{int(time.time())}.json"
            with open(diag_file, "w") as fh:
                json.dump({"verdict": verdict.summary(), "payload": payload}, fh, indent=2)
            return   # DO NOT dispatch to Machine B
        # ----------------------------------
"""

old_target = """    try:
        logging.info(f"[COGNITION_ROUTE] Pushing {payload['symbol']} signal to Direct HTTP Bridge...")"""

new_target = patch_code + """
        logging.info(f"[COGNITION_ROUTE] Pushing {payload['symbol']} signal to Direct HTTP Bridge...")"""

content = content.replace(old_target, new_target)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched sentinel_slow_loop.py")
