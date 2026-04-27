import os
import faiss
import numpy as np
import json

class EpisodicMemory:
    """
    Tier 1 & 2: Episodic Memory and Semantic Retrieval.
    Uses FAISS for high-performance similarity search on 93-dim state vectors.
    Expanded v142: Includes Kronos Prob, TFM P10/P90 Dist, HMM State.
    """
    def __init__(self, dim=93, index_path="C:\\Sentinel_Project\\sentinel_episodic.index", meta_path="C:\\Sentinel_Project\\sentinel_meta.json"):
        self.dim = dim
        self.index_path = index_path
        self.meta_path = meta_path
        self.metadata = {}
        
        # Load or create index
        if os.path.exists(self.index_path):
            try:
                self.index = faiss.read_index(self.index_path)
                if self.index.d != self.dim:
                    print(f"[MEMORY] Dimension mismatch ({self.index.d} vs {self.dim}). Resetting index.")
                    self.index = faiss.IndexFlatIP(self.dim)
                    self.metadata = {}
                else:
                    with open(self.meta_path, "r") as f:
                        self.metadata = json.load(f)
                    print(f"[MEMORY] Loaded index with {self.index.ntotal} episodes.")
            except Exception as e:
                print(f"[MEMORY] Load error: {e}. Creating fresh index.")
                self.index = faiss.IndexFlatIP(self.dim)
        else:
            self.index = faiss.IndexFlatIP(self.dim)
            print("[MEMORY] Created new FAISS IndexFlatIP (Cosine Similarity).")

    def _normalize(self, vector):
        """Helper to normalize vectors to unit length."""
        norm = np.linalg.norm(vector)
        if norm == 0: return vector
        return vector / norm

    def store(self, vector, action, pnl, reasoning, lesson="N/A"):
        """Stores a new normalized memory object."""
        v_norm = self._normalize(vector)
        vec = np.array([v_norm]).astype('float32')
        self.index.add(vec)
        
        idx = str(self.index.ntotal - 1)
        self.metadata[idx] = {
            "action": action,
            "pnl": pnl,
            "reasoning": reasoning,
            "lesson": lesson,
            "timestamp": str(np.datetime64('now'))
        }
        self.save()
        return idx

    def retrieve(self, query_vector, k=3):
        """Semantic Retrieval: Finds top-K similar past episodes (Cosine Similarity)."""
        if self.index.ntotal == 0:
            return []
            
        q_norm = self._normalize(query_vector)
        q = np.array([q_norm]).astype('float32')
        D, I = self.index.search(q, k)
        
        results = []
        for i, idx_val in enumerate(I[0]):
            if idx_val == -1: continue
            idx = str(idx_val)
            meta = self.metadata.get(idx, {})
            results.append({
                "distance": float(D[0][i]), # This is now the Inner Product (Cosine Similarity)
                "meta": meta
            })
        return results

    def save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.meta_path, "w") as f:
            json.dump(self.metadata, f, indent=2)

if __name__ == "__main__":
    # Test
    mem = EpisodicMemory(dim=93)
    dummy_state = np.random.randn(93)
    mem.store(dummy_state, "LONG", 150.0, "Breakout detected on M15")
    
    query = dummy_state + 0.01
    results = mem.retrieve(query, k=1)
    # distance is now the similarity score
    print(f"[MEMORY] Retrieved similarity: {results[0]['distance']:.4f}")
