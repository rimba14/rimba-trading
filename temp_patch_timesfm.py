import re

file_path = r'C:\Sentinel_Project\fastapi_sniper.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Define the new logic to inject into get_timesfm_sl_distance
new_logic = '''
    def _get_asset_multiplier(sym):
        if 'BTC' in sym or 'ETH' in sym: return 4.0
        if 'US30' in sym or 'NAS100' in sym or 'US2000' in sym or 'SPX500' in sym: return 4.0
        if 'XAU' in sym or 'XAG' in sym: return 4.0
        return 6.0

    constitutional_sl_distance = current_atr * _get_asset_multiplier(symbol)

    if timesfm_valid:
        raw_dist = abs(entry_price - p10) if direction == "BUY" else abs(p90 - entry_price)
        if raw_dist < constitutional_sl_distance:
            logger.warning(f"[{symbol}] SRE WARNING: TimesFM compression {raw_dist:.5f} < ATR Floor {constitutional_sl_distance:.5f}. Enforcing Structural Floor.")
        dist = max(raw_dist, constitutional_sl_distance)
        logger.info(f"[{symbol}] TimesFM SL active: distance={dist:.5f} (Floor protected)")
        return dist, True
    else:
        dist = constitutional_sl_distance
        logger.warning(f"[{symbol}] Coherence Protection Engaged: Fallback ATR SL active: distance={dist:.5f}")
        return dist, False
'''

# Find the end of get_timesfm_sl_distance and replace its return logic
pattern = re.compile(r'    if timesfm_valid:.*?return dist, False', re.DOTALL)
new_content = pattern.sub(new_logic.strip(), content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Patch applied to fastapi_sniper.py")
