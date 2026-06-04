import sys
sys.path.append('C:/Sentinel_Project')
try:
    from arcticdb import Arctic
    ac = Arctic('lmdb://C:/Sentinel_Project/data/arctic_cache')
    lib = ac.get_library('oracle_cache')
    print('Symbols in oracle_cache:', lib.list_symbols()[:20])
    for symbol in ['EURUSD_meta', 'BTCUSD_meta', 'GBPUSD_meta']:
        try:
            df = lib.read(symbol).data
            print(f'\nAUDIT FOR {symbol}:')
            print(f'  Keys: {df.keys()}')
        except Exception as e:
            print(f'\nAUDIT FOR {symbol}: Failed to read. Error: {e}')
except Exception as e:
    print('Failed to init arctic:', e)
