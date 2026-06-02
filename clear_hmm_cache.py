from arcticdb import Arctic
import logging

logging.basicConfig(level=logging.INFO)

try:
    store = Arctic("lmdb://./data/arctic_cache")
    if "oracle_cache" in store.list_libraries():
        lib = store["oracle_cache"]
        symbols = lib.list_symbols()
        purged = 0
        for sym in symbols:
            if sym.endswith("_wasserstein") or sym.endswith("_regime_metrics"):
                logging.info(f"Deleting symbol {sym} from oracle_cache...")
                lib.delete(sym)
                purged += 1
        logging.info(f"HMM Memory Exorcism: Purged {purged} symbols from oracle_cache.")
    
    # Check if a library named 'hmm_latent_states' exists, and if so, drop it.
    if "hmm_latent_states" in store.list_libraries():
        logging.info("Dropping library hmm_latent_states...")
        store.delete_library("hmm_latent_states")
        
    logging.info("HMM Cache Rebuilt successfully. System will now re-fit transition probabilities on active session data.")
except Exception as e:
    logging.error(f"Error rebuilding HMM cache: {e}")
