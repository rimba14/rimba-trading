import os
import numpy as np
from pymilvus import MilvusClient
import json
import time

class MilvusMemory:
    """
    Tier 1 & 2: Episodic Memory utilizing Milvus Lite.
    Provides sub-15ms retrieval latency with native JSON metadata support.
    """
    def __init__(self, dim=89, collection_name="sentinel_episodes", db_path="C:\\Sentinel_Project\\sentinel_milvus.db"):
        self.dim = dim
        self.collection_name = collection_name
        self.client = MilvusClient(db_path)
        
        # Create collection if not exists
        if not self.client.has_collection(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                dimension=self.dim,
                primary_field_name="id",
                id_type="int64",
                auto_id=True
            )
            print(f"[MILVUS] Created collection '{self.collection_name}'.")
        else:
            print(f"[MILVUS] Connected to collection '{self.collection_name}'.")

    def store(self, vector, action, pnl, reasoning, lesson="N/A"):
        """Stores a new memory object directly into Milvus."""
        # Convert reasoning/lesson to dict metadata
        data = [{
            "vector": vector.tolist() if isinstance(vector, np.ndarray) else vector,
            "action": action,
            "pnl": pnl,
            "reasoning": reasoning,
            "lesson": lesson,
            "timestamp": int(time.time())
        }]
        res = self.client.insert(collection_name=self.collection_name, data=data)
        return res["ids"][0]

    def retrieve(self, query_vector, k=3):
        """Semantic Retrieval: Finds top-K similar past episodes using L2 distance."""
        q_vec = query_vector.tolist() if isinstance(query_vector, np.ndarray) else query_vector
        
        search_res = self.client.search(
            collection_name=self.collection_name,
            data=[q_vec],
            limit=k,
            output_fields=["action", "pnl", "reasoning", "lesson"]
        )
        
        results = []
        for hit in search_res[0]:
            results.append({
                "distance": hit["distance"],
                "id": hit["id"],
                "meta": hit["entity"]
            })
        return results

if __name__ == "__main__":
    # Test
    mem = MilvusMemory(dim=89)
    dummy_state = np.random.randn(89).astype('float32')
    mem.store(dummy_state, "SHORT", -25.0, "Bearish divergence on H1")
    
    start = time.time()
    results = mem.retrieve(dummy_state, k=1)
    latency = (time.time() - start) * 1000
    print(f"[MILVUS] Retrieved in {latency:.2f}ms: {results}")
