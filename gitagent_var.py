import numpy as np
import pandas as pd

class portfolio_guardian:
    def __init__(self, confidence=0.99):
        self.confidence = confidence

    def calculate_returns(self, prices_dict):
        """
        Expects a dict of symbols to their historical close price arrays.
        """
        returns_df = pd.DataFrame()
        for sym, prices in prices_dict.items():
            returns_df[sym] = pd.Series(prices).pct_change().dropna()
        return returns_df

    def calculate_parametric_var(self, positions_usd, returns_df):
        """
        Variance-Covariance VaR calculation.
        positions_usd: dict {sym: usd_value_at_risk}
        """
        if returns_df.empty or len(positions_usd) == 0:
            return 0.0
        
        # 1. Weights
        symbols = list(positions_usd.keys())
        total_value = sum(positions_usd.values())
        weights = np.array([positions_usd[s] for s in symbols]) / total_value
        
        # 2. Covariance Matrix
        cov_matrix = returns_df[symbols].cov()
        
        # 3. Portfolio Variance: w^T * Cov * w
        port_variance = np.dot(weights.T, np.dot(cov_matrix, weights))
        port_std = np.sqrt(port_variance)
        
        # 4. Z-score (0.99 conf = 2.33, 0.95 conf = 1.65)
        z_score = 2.33 if self.confidence == 0.99 else 1.65
        
        var_pct = z_score * port_std
        var_usd = var_pct * total_value
        
        return var_usd

    def run_monte_carlo_var(self, positions_usd, returns_df, iterations=5000):
        """
        Monte Carlo VaR calculation.
        """
        if returns_df.empty or len(positions_usd) == 0:
            return 0.0
            
        symbols = list(positions_usd.keys())
        total_value = sum(positions_usd.values())
        weights = np.array([positions_usd[s] for s in symbols]) / total_value
        
        # Mean and Covariance
        mean_returns = returns_df[symbols].mean()
        cov_matrix = returns_df[symbols].cov()
        
        # Cholesky Decomposition
        try:
            chol = np.linalg.cholesky(cov_matrix)
        except np.linalg.LinAlgError:
            # Fallback if matrix is not positive definite
            # Use randomized Krylov subspace proxy instead of standard SVD
            try:
                from alpha_combiner import randomized_krylov_svd
                U, _, _ = randomized_krylov_svd(cov_matrix.values, rank=cov_matrix.shape[1])
                chol = U
            except Exception:
                chol = np.linalg.svd(cov_matrix)[0] # PCA-based alternative
            
        # Simulating correlated random returns
        sim_rets = np.random.normal(size=(iterations, len(symbols)))
        correlated_rets = np.dot(sim_rets, chol.T)
        
        # Adding back the mean (drift)
        applied_rets = correlated_rets + mean_returns.values
        
        # Portfolio Returns in each simulation
        portfolio_sim_rets = np.dot(applied_rets, weights)
        
        # Calculate VaR at specified percentile
        percentile = (1 - self.confidence) * 100
        var_pct = np.percentile(portfolio_sim_rets, percentile)
        
        # VaR is absolute loss
        var_usd = abs(var_pct) * total_value
        return var_usd

    def calculate_net_beta(self, positions, returns_df, benchmark='NAS100'):
        """
        Calculates aggregate portfolio beta relative to a benchmark.
        positions: dict {sym: usd_value}
        returns_df: DataFrame of historical returns for all syms + benchmark.
        """
        if returns_df.empty or benchmark not in returns_df.columns or not positions:
            return 0.0
            
        betas = {}
        bench_rets = returns_df[benchmark]
        bench_var = bench_rets.var()
        if bench_var == 0: return 0.0
        
        for sym in positions.keys():
            if sym in returns_df.columns:
                cov = returns_df[sym].cov(bench_rets)
                betas[sym] = cov / bench_var
            else:
                betas[sym] = 1.0 # default to unit beta if unknown
                
        total_value = sum(positions.values())
        pos_values = np.array([positions[s] for s in positions.keys()])
        beta_values = np.array([betas[s] for s in positions.keys()])
        net_beta = np.dot(pos_values / total_value, beta_values)
        return net_beta

guardian = portfolio_guardian()

if __name__ == "__main__":
    # Test with mockup data
    # EURUSD and GBPUSD (highly correlated)
    df = pd.DataFrame({
        'EURUSD': np.random.normal(0.0001, 0.005, 100),
        'GBPUSD': np.random.normal(0.0001, 0.005, 100)
    })
    # Add high correlation manually
    df['GBPUSD'] = df['EURUSD'] * 0.8 + np.random.normal(0, 0.001, 100)
    
    pos = {'EURUSD': 1000, 'GBPUSD': 1000}
    linear_risk = sum(pos.values()) * 0.01 # 1% simple risk
    
    p_var = guardian.calculate_parametric_var(pos, df)
    m_var = guardian.run_monte_carlo_var(pos, df)
    
    print(f"Linear Risk Sum: ${linear_risk:.2f}")
    print(f"Parametric VaR (99%): ${p_var:.2f}")
    print(f"Monte Carlo VaR (99%): ${m_var:.2f}")
