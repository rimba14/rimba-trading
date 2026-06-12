import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance
from sklearn.cluster import KMeans
import logging

class WassersteinRegimeCluster:
    """
    Perception Layer Module: Wasserstein Optimal Transport (v30.0)
    Clusters rolling sequences of fractionally differentiated prices into discrete 
    market regimes using Wasserstein distance.
    """
    def __init__(self, window_size=50, n_clusters=3):
        self.window_size = window_size
        self.n_clusters = n_clusters
        self.kmeans = None
        self.regime_labels = {}
        
        # Predefined stylized distributions (quantiles) for zero-lag bootstrapping
        np.random.seed(42)
        dist_trend = np.sort(np.random.normal(0.0005, 0.002, window_size))       # Low-Vol Trend
        dist_mean_rev = np.sort(np.random.normal(0.0, 0.01, window_size))         # High-Vol Mean Reversion
        dist_crisis = np.sort(np.random.standard_t(df=3, size=window_size) * 0.015 - 0.005) # Crisis Tail
        
        self.bootstrapped_centroids = np.vstack([dist_trend, dist_mean_rev, dist_crisis])
        self.regime_names = ["LOW-VOL TREND", "HIGH-VOL MEAN REVERSION", "CRISIS TAIL"]

    def _assign_labels_to_centroids(self, centroids):
        """
        Dynamically map generic K-Means clusters to semantic regime names 
        based on volatility (variance) and drift (mean).
        """
        metrics = []
        for i, centroid in enumerate(centroids):
            mean_val = np.mean(centroid)
            std_val = np.std(centroid)
            metrics.append((i, mean_val, std_val))
            
        # Sort by volatility
        metrics.sort(key=lambda x: x[2])
        
        # Lowest vol is Trend
        trend_idx = metrics[0][0]
        # Highest vol is Crisis Tail
        crisis_idx = metrics[2][0]
        # Middle vol is Mean Reversion
        mean_rev_idx = metrics[1][0]
        
        self.regime_labels[trend_idx] = "LOW-VOL TREND"
        self.regime_labels[mean_rev_idx] = "HIGH-VOL MEAN REVERSION"
        self.regime_labels[crisis_idx] = "CRISIS TAIL"

    def fit_historical(self, series: pd.Series):
        """
        Fits the K-means model on historical fractionally differentiated prices.
        Since we are in 1D, L2 distance on sorted arrays is equivalent to 2-Wasserstein distance.
        """
        series = series.pct_change().dropna()
        if len(series) < self.window_size * 2:
            logging.warning("[Wasserstein] Not enough historical data to fit K-Means. Using stylized bootstraps.")
            return

        # Create rolling windows
        rolling_windows = []
        for i in range(len(series) - self.window_size + 1):
            window = series.iloc[i:i + self.window_size].values
            # Sort to get empirical quantile function (inverse CDF)
            rolling_windows.append(np.sort(window))
            
        X = np.array(rolling_windows)
        
        self.kmeans = KMeans(n_clusters=self.n_clusters, random_state=42, n_init=10)
        self.kmeans.fit(X)
        
        self._assign_labels_to_centroids(self.kmeans.cluster_centers_)
        logging.info("[Wasserstein] Successfully fitted historical distributions and mapped regimes.")

    def get_current_state(self, live_window: np.ndarray):
        """
        Calculates the Wasserstein distance between the live window and the centroids.
        Returns the regime name, probabilities, and distances.
        """
        if len(live_window) < 10:
            return "LOW-VOL TREND", 1.0, {"LOW-VOL TREND": 1.0}
            
        # Convert raw prices to returns to match the stylized return centroids
        live_returns = np.diff(live_window) / (live_window[:-1] + 1e-9)
            
        # Ensure we have the exact window size for vectorized distance if possible
        if len(live_returns) > self.window_size:
            live_returns = live_returns[-self.window_size:]
            
        live_dist = np.sort(live_returns)
        
        centroids_to_use = self.kmeans.cluster_centers_ if self.kmeans else self.bootstrapped_centroids
        label_map = self.regime_labels if self.kmeans else {0: "LOW-VOL TREND", 1: "HIGH-VOL MEAN REVERSION", 2: "CRISIS TAIL"}
        
        distances = {}
        for i, centroid in enumerate(centroids_to_use):
            # Compute 1-Wasserstein distance using scipy
            dist = wasserstein_distance(live_dist, centroid)
            regime_name = label_map[i]
            distances[regime_name] = dist
            
        # Closest centroid
        closest_regime = min(distances, key=distances.get)
        
        # Softmax of inverse distances for pseudo-probabilities
        inv_distances = {k: 1.0 / (d + 1e-6) for k, d in distances.items()}
        sum_inv = sum(inv_distances.values())
        probs = {k: v / sum_inv for k, v in inv_distances.items()}
        
        return closest_regime, probs[closest_regime], probs
