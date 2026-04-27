import faiss
import numpy as np
import logging
import time
import os

class EpisodicMemoryAuditor:
    def __init__(self, index_path="C:/Sentinel_Project/sentinel_episodic.index"):
        """
        Loads the FAISS index into RAM exactly once during system initialization.
        Ensures zero disk I/O during the 1-second Fast Loop.
        """
        try:
            if not os.path.exists(index_path):
                logging.error(f"FAISS index not found at {index_path}")
                self.is_loaded = False
                return

            # Note: Existing index sentinel_episodic.index was built with IndexFlatL2.
            # L2 distance (d) to Similarity (s) conversion: s = 1 / (1 + d)
            self.legend_index = faiss.read_index(index_path)
            self.is_loaded = True
            logging.info(f"Phase 3: FAISS Legend Archive loaded. Total vectors: {self.legend_index.ntotal}")
        except Exception as e:
            logging.error(f"Failed to load FAISS index: {e}")
            self.is_loaded = False

    def check_legend_override(self, live_vector: np.ndarray) -> tuple[bool, float]:
        """
        Executes a blazing-fast memory comparison (< 2 milliseconds).
        Returns (is_override, similarity_score)
        """
        if not self.is_loaded or live_vector is None:
            return False, 0.0

        # 1. Ensure the incoming vector is exactly 2D: (1, Dimension) and float32
        if live_vector.dtype != np.float32:
            live_vector = live_vector.astype(np.float32)
        
        if len(live_vector.shape) == 1:
            live_vector = np.expand_dims(live_vector, axis=0)

        # 2. Execute L2 Search
        start_time = time.perf_counter()
        distances, indices = self.legend_index.search(live_vector, k=1)
        latency_ms = (time.perf_counter() - start_time) * 1000

        # Convert L2 distance to Similarity score (0 to 1)
        # Note: If distances[0][0] is 0, similarity is 1.0
        best_l2_dist = distances[0][0]
        best_similarity = 1.0 / (1.0 + best_l2_dist)
        match_index = indices[0][0]

        # 3. Evaluate the Override Threshold (85% Similarity)
        if best_similarity >= 0.85:
            logging.warning(
                f"LEGEND OVERRIDE TRIGGERED! Sim: {best_similarity:.2%} | "
                f"Index: {match_index} | Latency: {latency_ms:.2f}ms"
            )
            return True, best_similarity

        return False, best_similarity
