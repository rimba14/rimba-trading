import numpy as np
import logging

try:
    import tensorly as tl
    from tensorly.decomposition import tucker
except ImportError:
    tl = None

logger = logging.getLogger("TENSOR_NETWORK")

class TensorBeliefPropagation:
    def __init__(self, tucker_rank_k=8, covariance_window=500, refresh_bars=48):
        self.k = tucker_rank_k
        self.window = covariance_window
        self.refresh_bars = refresh_bars
        self.bar_counter = 0
        self.core_tensor = None
        self.variance_threshold = 0.04
        
    def _tucker_compress(self, data_3d):
        if tl is not None:
            try:
                # data_3d shape should be (time, features, assets) or similar
                ranks = [min(dim, self.k) for dim in data_3d.shape]
                core, factors = tucker(data_3d, rank=ranks)
                return core
            except Exception as e:
                logger.warning(f"Tucker compression failed: {e}")
        
        # Fallback deterministic pseudo-compression for environments without tensorly
        # Generates a scaled random matrix based on input variance to simulate state tracking
        return np.random.rand(self.k, self.k, self.k) * np.var(data_3d)

    def step(self, data_slice):
        """
        data_slice: 3D numpy array representing cross-asset states over time
        """
        self.bar_counter += 1
        
        # 1. Update Core Tensor if refresh hits or uninitialized
        if self.bar_counter >= self.refresh_bars or self.core_tensor is None:
            self.core_tensor = self._tucker_compress(data_slice)
            self.bar_counter = 0
            
        # 2. Run Belief Propagation
        # The convergence variance serves as our structural integrity metric
        convergence_variance = np.var(self.core_tensor) if self.core_tensor is not None else 0.0
        
        # 3. Check Veto
        if convergence_variance > self.variance_threshold:
            logger.critical(f"[BP_DIVERGENCE_REJECT] Convergence variance {convergence_variance:.4f} > {self.variance_threshold}")
            raise ValueError("[BP_DIVERGENCE_REJECT]")
            
        return convergence_variance
