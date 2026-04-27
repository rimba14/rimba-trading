from arcticdb import Arctic

def migrate():
    try:
        # Increase map_size to 10GB for the mass purge
        a = Arctic("lmdb://C:\\sentinel_arctic?map_size=10GB")
        
        if "trading_edge" in a.list_libraries():
            print("Wiping 'trading_edge' library to reset all schemas...")
            a.delete_library("trading_edge")
            
        print("Creating fresh 'trading_edge' library...")
        a.create_library("trading_edge")
        print("Migration complete. All schemas reset.")
                
        print("Migration complete. Ready for new schema.")
    except Exception as e:
        print(f"FATAL MIGRATION ERROR: {e}")

if __name__ == "__main__":
    migrate()
