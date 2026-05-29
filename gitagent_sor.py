import MetaTrader5 as mt5
import numpy as np

class triangular_finder:
    def __init__(self):
        # Common FX Triads
        # Keys are the target pair, values are the list of legs to synthesize it.
        # Format: (Symbol, Side_Multiplier) 
        # Side_Multiplier: 1 if side matches target, -1 if side must be flipped
        self.triads = {
            "EURUSD": [
                [("EURGBP", 1), ("GBPUSD", 1)],
                [("EURJPY", 1), ("USDJPY", -1)],
                [("EURCHF", 1), ("USDCHF", -1)]
            ],
            "GBPUSD": [
                [("EURUSD", 1), ("EURGBP", -1)],
                [("GBPJPY", 1), ("USDJPY", -1)]
            ],
            "USDJPY": [
                [("EURJPY", 1), ("EURUSD", -1)],
                [("GBPJPY", 1), ("GBPUSD", -1)]
            ]
        }

    def get_path_cost(self, path):
        """ Calculate total points/spread for a multi-leg path + verify tick """
        total_points = 0
        for symbol, _ in path:
            si = mt5.symbol_info(symbol)
            tick = mt5.symbol_info_tick(symbol)
            if si is None or tick is None: return 999999
            total_points += si.spread
        return total_points

    def find_best_route(self, symbol, side):
        """
        Returns: (is_synthetic, path_list)
        path_list: [(symbol, side_for_this_leg), ...]
        """
        # 1. Direct Path
        si = mt5.symbol_info(symbol)
        if si is None: return False, [], 999999, 999999
        
        direct_cost = si.spread
        best_cost = direct_cost
        best_path = [(symbol, side)]
        is_synthetic = False
        
        # 2. Check Triads
        if symbol in self.triads:
            for triad in self.triads[symbol]:
                cost = self.get_path_cost(triad)
                if cost < best_cost:
                    # Synthetic found!
                    best_cost = cost
                    is_synthetic = True
                    # Calculate legs
                    best_path = []
                    for leg_sym, multiplier in triad:
                        # If target side is BUY (1) and leg multiplier is 1 -> BUY
                        # If target side is BUY (1) and leg multiplier is -1 -> SELL
                        # If target side is SELL (-1) and leg multiplier is 1 -> SELL
                        # If target side is SELL (-1) and leg multiplier is -1 -> BUY
                        target_val = 1 if side == mt5.ORDER_TYPE_BUY else -1
                        leg_val = target_val * multiplier
                        leg_side = mt5.ORDER_TYPE_BUY if leg_val == 1 else mt5.ORDER_TYPE_SELL
                        best_path.append((leg_sym, leg_side))
        
        return is_synthetic, best_path, best_cost, direct_cost

sor = triangular_finder()

def get_sor_path(symbol, side):
    """ Public wrapper """
    return sor.find_best_route(symbol, side)

def randomized_krylov_svd(A: np.ndarray, rank: int, n_iter: int = 2, oversample: int = 5) -> tuple:
    """
    Computes a randomized block-Krylov subspace low-rank approximation of matrix A.
    Avoids standard multi-pass SVD in live execution windows.
    Returns (U, S, Vt).
    """
    try:
        if A.ndim != 2:
            raise ValueError("Input matrix A must be 2D")
        m, n = A.shape
        l = min(m, n, rank + oversample)
        # Random starting matrix
        Omega = np.random.normal(size=(n, l))
        
        # Power iteration (Krylov subspace generation)
        Y = A @ Omega
        for _ in range(n_iter):
            Q, _ = np.linalg.qr(Y, mode='reduced')
            Y = A @ (A.T @ Q)
            
        Q, _ = np.linalg.qr(Y, mode='reduced')
        B = Q.T @ A
        U_tilde, S, Vt = np.linalg.svd(B, full_matrices=False)
        U = Q @ U_tilde
        return U[:, :rank], S[:rank], Vt[:rank, :]
    except Exception as e:
        # Fallback to standard SVD under try-except wrapper to guarantee zero downtime
        try:
            U, S, Vt = np.linalg.svd(A, full_matrices=False)
            return U[:, :rank], S[:rank], Vt[:rank, :]
        except Exception:
            # Absolute recovery fallback
            U = np.eye(A.shape[0])
            S = np.ones(min(A.shape))
            Vt = np.eye(A.shape[1])
            return U[:, :rank], S[:rank], Vt[:rank, :]

if __name__ == "__main__":
    mt5.initialize()
    res = get_sor_path("EURUSD", mt5.ORDER_TYPE_BUY)
    print(f"SYM: EURUSD | Synthetic: {res[0]} | Path: {res[1]} | Cost: {res[2]} vs Direct: {res[3]}")
    mt5.shutdown()
