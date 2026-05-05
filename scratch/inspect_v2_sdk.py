import py_clob_client_v2
import inspect
print("--- py_clob_client_v2 members ---")
for name, obj in inspect.getmembers(py_clob_client_v2):
    if not name.startswith('_'):
        print(name)

try:
    from py_clob_client_v2.client import ClobClient
    print("\nSUCCESS: Found ClobClient in .client")
except ImportError:
    print("\nFAILED: ClobClient not in .client")

try:
    from py_clob_client_v2.clob_types import ApiCreds, OrderArgs
    print("SUCCESS: Found ApiCreds, OrderArgs in .clob_types")
except ImportError:
    print("FAILED: ApiCreds, OrderArgs not in .clob_types")
