file_path = r"C:\Sentinel_Project\fastapi_sniper.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

patch1 = """
    # Scale lot by health_size_multiplier from dynamic_risk_params.json
"""
new_patch1 = """
    # v30.60 HIGH-VOL RANGE Scenario B: 50% Sizing Reduction
    active_regime_for_sizing = "RANGE"
    try:
        from arcticdb import Arctic
        store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
        row = store["oracle_cache"].read(f"{symbol}_meta").data.iloc[-1]
        active_regime_for_sizing = str(row["wasserstein_state"]).upper()
    except:
        pass
    
    if active_regime_for_sizing in ["HIGH_VOLATILITY", "HIGH-VOL RANGE"]:
        lot = lot * 0.50
        logger.info(f"[{symbol}] [SCENARIO B] HIGH-VOL RANGE detected. Lot size reduced by 50% to {lot:.4f}")

    # Scale lot by health_size_multiplier from dynamic_risk_params.json
"""
if "HIGH-VOL RANGE Scenario B: 50% Sizing Reduction" not in content:
    content = content.replace(patch1, new_patch1)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patched fastapi_sniper.py lot sizing.")
