file_path = r"C:\Sentinel_Project\profit_manager_v28_34.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

patch2 = """        d_target = abs(target_tp - entry)
        d_guard = 0.80 * d_target"""

new_patch2 = """        d_target = abs(target_tp - entry)
        
        # Determine active regime for D_guard (v30.60 RANGE Logic)
        active_regime_for_guard = "TRENDING"
        try:
            from arcticdb import Arctic
            store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
            row = store["oracle_cache"].read(f"{pos.symbol}_meta").data.iloc[-1]
            active_regime_for_guard = str(row["wasserstein_state"]).upper()
        except:
            pass
        
        if "RANGE" in active_regime_for_guard:
            d_guard = 0.50 * d_target
        else:
            d_guard = 0.80 * d_target
"""
content = content.replace(patch2, new_patch2)

patch3 = """        trail_allowed = (d_current >= d_guard)"""
new_patch3 = """        trail_allowed = (d_current >= d_guard)
        
        # Scenario A: Terminal RANGE Harvest
        if "RANGE" in active_regime_for_guard and d_current >= d_guard and not ps.zone1_done:
            logger.info(f"[RANGE_HARVEST] {pos.symbol} breached D_guard {d_guard:.5f} in RANGE. Harvesting 75%.")
            tick = mt5.symbol_info_tick(pos.symbol)
            info = mt5.symbol_info(pos.symbol)
            if safe_scale_out(pos, ps, 0.75, "RANGE_TERMINAL_HARVEST", info, tick):
                ps.zone1_done = True
"""
if "Terminal RANGE Harvest" not in content:
    content = content.replace(patch3, new_patch3)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patched profit_manager_v28_34.py for RANGE handling.")
