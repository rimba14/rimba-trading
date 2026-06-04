import re
file_path = r'C:\Sentinel_Project\fastapi_sniper.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

bad_indent = '''def _get_asset_multiplier(sym):
        if 'BTC' in sym or 'ETH' in sym: return 4.0
        if 'US30' in sym or 'NAS100' in sym or 'US2000' in sym or 'SPX500' in sym: return 4.0
        if 'XAU' in sym or 'XAG' in sym: return 4.0
        return 6.0

    constitutional_sl_distance = current_atr * _get_asset_multiplier(symbol)'''

good_indent = '''    def _get_asset_multiplier(sym):
        if 'BTC' in sym or 'ETH' in sym: return 4.0
        if 'US30' in sym or 'NAS100' in sym or 'US2000' in sym or 'SPX500' in sym: return 4.0
        if 'XAU' in sym or 'XAG' in sym: return 4.0
        return 6.0

    constitutional_sl_distance = current_atr * _get_asset_multiplier(symbol)'''

content = content.replace(bad_indent, good_indent)
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Indentation fixed.")
