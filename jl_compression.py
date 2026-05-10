import numpy as np
import os
import pickle
from sklearn.random_projection import GaussianRandomProjection

class JLCompressor:
    """
    v23.3: Johnson-Lindenstrauss (JL) Lemma Compression Node.
    Ensures high-dimensional feature vectors are projected into a lower-dimensional
    subspace while preserving pairwise distances (up to epsilon).
    """
    _instance = None
    _matrix_path = r"C:\Sentinel_Project\jl_projection_matrix.pkl"

    def __new__(cls, input_dim=768, target_dim=128):
        if cls._instance is None:
            cls._instance = super(JLCompressor, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, input_dim=768, target_dim=128):
        if self._initialized:
            return
        
        self.input_dim = input_dim
        self.target_dim = target_dim
        self.transformer = None

        if os.path.exists(self._matrix_path):
            try:
                with open(self._matrix_path, 'rb') as f:
                    self.transformer = pickle.load(f)
                print(f"[JL_COMPRESSION] Matrix loaded from {self._matrix_path}. Target dim: {self.transformer.n_components}")
            except Exception as e:
                print(f"[JL_COMPRESSION] Error loading matrix: {e}. Re-initializing...")

        if self.transformer is None:
            print(f"[JL_COMPRESSION] Initializing new Gaussian Random Projection matrix ({input_dim} -> {target_dim})...")
            self.transformer = GaussianRandomProjection(n_components=target_dim, random_state=42)
            # Fit on a dummy identity matrix to lock the components
            dummy_data = np.random.randn(10, input_dim)
            self.transformer.fit(dummy_data)
            
            with open(self._matrix_path, 'wb') as f:
                pickle.dump(self.transformer, f)
            print(f"[JL_COMPRESSION] Matrix persisted to {self._matrix_path}.")

        self._initialized = True

    def compress(self, vector: np.ndarray) -> np.ndarray:
        """
        Compresses a high-dimensional vector or batch of vectors.
        """
        if vector.ndim == 1:
            vector = vector.reshape(1, -1)
        
        # Ensure dimensions match
        if vector.shape[1] != self.input_dim:
            # Fallback/Padding for mismatch (though v23.3 requires strict alignment)
            if vector.shape[1] < self.input_dim:
                padding = np.zeros((vector.shape[0], self.input_dim - vector.shape[1]))
                vector = np.hstack([vector, padding])
            else:
                vector = vector[:, :self.input_dim]

        compressed = self.transformer.transform(vector)
        return compressed.astype('float32')

if __name__ == "__main__":
    # Diagnostic test
    compressor = JLCompressor(input_dim=768, target_dim=128)
    dummy_vec = np.random.randn(1, 768)
    compressed = compressor.compress(dummy_vec)
    print(f"Original shape: {dummy_vec.shape}")
    print(f"Compressed shape: {compressed.shape}")
    assert compressed.shape == (1, 128)
    print("JL Compression Diagnostic: SUCCESS")
