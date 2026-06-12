import os
import faiss
import numpy as np
import json
import time
from gitagent_types import MemoryEpisode

class FastMemory:
    """
    Tier 1 & 2: Optimized Episodic Memory using FAISS.
    Compatible with Python 3.14 and optimized for sub-10ms retrieval.
    """
    def __init__(self, dim=89, index_path="C:\\Sentinel_Project\\sentinel_fast.index", meta_path="C:\\Sentinel_Project\\sentinel_fast_meta.json"):
        self.dim = dim
        self.index_path = index_path
        self.meta_path = meta_path
        self.metadata = {}
        
        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.meta_path, "r") as f:
                self.metadata = json.load(f)
        else:
            self.index = faiss.IndexFlatL2(self.dim)

    def store(self, episode: MemoryEpisode):
        """Stores a new memory object encapsulated in MemoryEpisode."""
        vec = np.array([episode.vector]).astype('float32')
        self.index.add(vec)
        idx = str(self.index.ntotal - 1)
        self.metadata[idx] = {
            "action": episode.action,
            "pnl": episode.pnl,
            "reasoning": episode.reasoning,
            "lesson": episode.lesson,
            "timestamp": int(time.time())
        }
        self.save()
        return idx

    def retrieve(self, query_vector, k=3):
        if self.index.ntotal == 0: return []
        q = np.array([query_vector]).astype('float32')
        D, I = self.index.search(q, k)
        results = []
        for idx_val in I[0]:
            if idx_val == -1: continue
            results.append({"meta": self.metadata.get(str(idx_val), {})})
        return results

    def save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.meta_path, "w") as f:
            json.dump(self.metadata, f, indent=2)
