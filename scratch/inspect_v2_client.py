from py_clob_client_v2.client import ClobClient
import inspect
print("--- ClobClient members ---")
for name, obj in inspect.getmembers(ClobClient):
    if not name.startswith('_'):
        print(name)
