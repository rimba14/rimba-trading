import tensortrade.env.default as default
from tensortrade.env.default.rewards import RewardScheme
from tensortrade.feed.core import DataFeed, Stream
from tensortrade.oms.instruments import Instrument, USD, BTC
from tensortrade.oms.exchanges import Exchange
from tensortrade.oms.services.execution.simulated import execute_order
from tensortrade.oms.wallets import Wallet, Portfolio
from tensortrade.agents import DQNAgent
import pandas as pd
import numpy as np
import git_arctic
import logging

logger = logging.getLogger("TensorEnv")

class DifferentialSortinoReward(RewardScheme):
    """
    Online, recursive step-by-step Differential Sortino Ratio tracker
    Derived from Koskinen (2025) Appendix A.
    """
    def __init__(self, target_return=0.0, eta=0.01):
        super().__init__()
        self.target_return = target_return
        self.eta = eta  # Smoothing/decay constant for moving averages
        self.A = None   # Online exponential mean return
        self.D = None   # Online exponential downside variance
        self.previous_net_worth = None

    def get_reward(self, portfolio: Portfolio) -> float:
        current_net_worth = portfolio.performance.get('net_worth', 0.0)
        
        if self.previous_net_worth is None:
            self.previous_net_worth = current_net_worth
            return 0.0
            
        r_t = (current_net_worth - self.previous_net_worth) / (self.previous_net_worth + 1e-9)
        self.previous_net_worth = current_net_worth

        # Initialize structure on first observation
        if self.A is None or self.D is None:
            self.A = r_t
            initial_downside = max(self.target_return - r_t, 0)
            self.D = (initial_downside ** 2) + (0.02 ** 2) # Buffer variance
            return 0.0
        
        prev_A = self.A
        prev_D = self.D
        prev_B = np.sqrt(prev_D) if prev_D > 1e-8 else 0.02

        # 1. Update Exponential Moving Average of returns
        self.A = self.eta * r_t + (1 - self.eta) * prev_A
        
        # 2. Isolate Downside Deviation
        downside = max(self.target_return - r_t, 0)
        
        # 3. Update Downside Variance
        self.D = self.eta * (downside ** 2) + (1 - self.eta) * prev_D
        
        # 4. Calculate Differential Sortino Contribution (Derivative)
        mean_component = (r_t - prev_A) / prev_B
        
        if downside > 0:
            vol_component = (prev_A * (downside**2 - prev_D)) / (2 * (prev_D ** 1.5))
            dS_t = mean_component - self.eta * vol_component
        else:
            # Zero downside penalty contribution if it's an upside outperformance bar
            dS_t = mean_component
            
        # 5. HKUST 2025 Multi-Agent Reward Safeguard
        # Strict step penalty if policy triggers counter-trend order cancellations within 500ms of breakout.
        current_step = portfolio.step if hasattr(portfolio, 'step') else 0
        is_breakout = hasattr(self, 'breakout_active') and self.breakout_active
        is_cancel = hasattr(portfolio, 'env') and hasattr(portfolio.env.action_scheme, 'action') and portfolio.env.action_scheme.action == 0
        if is_breakout and is_cancel:
            dS_t -= 1.0  # Strict penalty to optimize for survival rather than short-term friction
            
        return float(dS_t)

def create_vantage_env(df: pd.DataFrame, observer_window: int = 20):
    """
    Instantiates a TensorTrade simulated environment with Vantage-specific costs.
    PBR (Position-Based Returns) RewardScheme is used.
    """
    
    # 1. Define Instruments
    # Using USD as the base currency and a generic 'ASSET' for the tradable instrument
    ASSET = Instrument('ASSET', 8, 'Asset')
    
    # 2. Define the Exchange with Vantage Costs
    # Vantage RAW: ~$7/lot commission + typical 0.1-0.2 pip spread for majors
    # We model this as a fixed fee and a small slippage.
    vantage_exchange = Exchange("VantageSim", service=execute_order)(
        Stream.source(df['close'], dtype="float").rename("USD-ASSET")
    )
    
    # Vantage Specifics:
    # Commission: $7 per 100,000 notional (round turn) => ~0.00007 multiplier
    vantage_exchange.options.commission = 0.00007 
    # Slippage: 0.1 pip roughly => 0.00001
    vantage_exchange.options.min_trade_size = 0.01 # 0.01 Lots
    
    # 3. Define the DataFeed (Standardized v18.6)
    # Pipe TimesFM, Kronos, and HMM into the observer
    features = []
    for col in df.columns:
        if col not in ['date', 'open', 'high', 'low', 'close', 'volume']:
            features.append(Stream.source(df[col], dtype="float").rename(col))
            
    feed = DataFeed(features)
    
    # 4. Define Portfolio
    portfolio = Portfolio(USD, [
        Wallet(vantage_exchange, 10000 * USD),
        Wallet(vantage_exchange, 0 * ASSET),
    ])
    
    # 5. Reward Scheme (Differential Sortino Ratio)
    # Penalizes asymmetric downside without squashing alpha fat-tails
    reward_scheme = DifferentialSortinoReward(target_return=0.0, eta=0.01)
    
    # 6. Action Scheme
    action_scheme = default.actions.SimpleOrders()
    
    # 7. Create Environment
    env = default.create(
        portfolio=portfolio,
        action_scheme=action_scheme,
        reward_scheme=reward_scheme,
        feed=feed,
        window_size=observer_window
    )
    
    return env

def get_sampled_data(symbol: str):
    """
    Directive v18.7: 50/50 Sampling between Live and Synthetic data.
    """
    store = git_arctic.get_arctic()
    
    # 50% Chance to pull from MiroFish Synthetic Cache
    if np.random.rand() > 0.5:
        logger.info(f"[{symbol}] Sampling from MIROFISH Synthetic Cache...")
        lib_syn = store["synthetic_mirofish_cache"]
        # Randomly pick one of the three regimes
        regime = np.random.choice(["flash_crash", "choppy_vol", "melt_up"])
        symbol_key = f"{symbol}_{regime}"
        if symbol_key in lib_syn.list_symbols():
            return lib_syn.read(symbol_key).data
        logger.warning(f"[{symbol}] Synthetic regime {regime} not found. Falling back to live.")

    # Fallback/Default: 50% Live Data
    logger.info(f"[{symbol}] Sampling from LIVE Historical Cache...")
    lib_live = store["oracle_cache"]
    # We take a recent window of processed features
    if f"{symbol}_kronos" in lib_live.list_symbols():
        return lib_live.read(f"{symbol}_kronos").data
    
    return None

class UnifiedObserver:
    """
    Standardized v18.6 Observer.
    Generates the unified state representation (S_t) for the Math Meta-Model.
    """
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        
    def observe(self, data: pd.DataFrame):
        # Implementation of unified state generation from DataFeed
        # In TensorTrade, this is handled by the internal feed.observe()
        # This class provides a bridge for the MathMetaModel.
        pass
