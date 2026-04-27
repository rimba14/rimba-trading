import pandas as pd
import os
from datetime import datetime

class ArcticLibrary:
    def __init__(self, name, path):
        self.name = name
        self.base_path = os.path.join(path, name)
        os.makedirs(self.base_path, exist_ok=True)
        
    def append(self, symbol, df):
        """Append to symbol's parquet store."""
        file_path = os.path.join(self.base_path, f"{symbol}.parquet")
        if os.path.exists(file_path):
            existing = pd.read_parquet(file_path)
            # Ensure index alignment
            updated = pd.concat([existing, df])
            # Keep unique index if it's time-based
            updated = updated[~updated.index.duplicated(keep='last')]
            updated.to_parquet(file_path)
        else:
            df.to_parquet(file_path)
            
    def write(self, symbol, df):
        """Standard write (version-replacement simulation)."""
        file_path = os.path.join(self.base_path, f"{symbol}.parquet")
        df.to_parquet(file_path)
        
    def read(self, symbol):
        """Read latest version."""
        file_path = os.path.join(self.base_path, f"{symbol}.parquet")
        if os.path.exists(file_path):
            class VersionedItem:
                def __init__(self, data):
                    self.data = data
            return VersionedItem(pd.read_parquet(file_path))
        return None

class Arctic:
    def __init__(self, uri):
        # Convert lmdb://C:\\sentinel_arctic to C:\\sentinel_arctic
        self.path = uri.replace("lmdb://", "").replace("sqlitC:\\Sentinel_Project\\/", "")
        if ":" not in self.path and not self.path.startswith("/"):
            self.path = os.path.abspath(self.path)
        os.makedirs(self.path, exist_ok=True)
        
    def get_library(self, name):
        return ArcticLibrary(name, self.path)
        
    def list_libraries(self):
        if not os.path.exists(self.path): return []
        return [d for d in os.listdir(self.path) if os.path.isdir(os.path.join(self.path, d))]
        
    def create_library(self, name):
        os.makedirs(os.path.join(self.path, name), exist_ok=True)
        return self.get_library(name)

if __name__ == "__main__":
    # Internal Unit Test
    import numpy as np
    a = Arctic("lmdb://C:\\Sentinel_Project\\arctic_poly_test")
    lib = a.create_library("test_lib")
    df = pd.DataFrame({'val': [1,2,3]}, index=pd.to_datetime(['2026-01-01', '2026-01-02', '2026-01-03']))
    lib.write("AAPL", df)
    res = lib.read("AAPL")
    assert len(res.data) == 3
    print("Polyfill Diagnostic Passed.")
