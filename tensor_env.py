import tensortrade.env.default as default
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
    
    # 5. Reward Scheme (Dense, Cost-Aware PBR)
    # Position-Based Returns (PBR) penalizes churn and rewards holding profitable convictions.
    reward_scheme = default.rewards.PBR()
    
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

