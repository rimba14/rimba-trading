import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import gitagent_happo as happo
from datetime import datetime, timedelta, timezone
import torch

def generate_training_data(days=7):
    if not mt5.initialize(): return []
    
    # 1. Fetch symbols
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "NAS100", "SP500", "BTCUSD"]
    trajectories = []
    
    print(f"[TRAIN] Harvesting last {days} days of trajectories...")
    
    for sym in symbols:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 500)
        if rates is None: continue
        df = pd.DataFrame(rates)
        
        # 2. Simulate observation states (Simplified for calibration)
        # In a real setup, we'd use the full agent scores. 
        # Here we use 'Future Returns' as the ground truth reward.
        
        for i in range(100, len(df)-20):
            window = df.iloc[i-100:i]
            future_return = (df['close'].iloc[i+20] - df['close'].iloc[i]) / df['close'].iloc[i]
            
            # Simulated Agent Observations
            obs = {
                'trend':     [np.random.normal(0.5, 0.1), np.random.normal(0.0, 0.2), 1.0],
                'structure': [np.random.normal(0.0, 0.2), 0.0, 0.0],
                'flow':      [np.random.normal(1.0, 0.5), 0.0, 0.0],
                'deep':      [np.random.normal(0.0, 0.3), 0.5, np.random.normal(0.0, 0.5)],
                'macro':     [0.0, 0.0, 0.0]
            }
            
            # Global state (concat)
            global_state = []
            for name in happo.AGENT_ORDER: global_state.extend(obs[name])
            
            # Ground truth: if future_return > 0.002, action=1 (BUY); < -0.002, action=2 (SELL); else 0 (HOLD)
            action = 1 if future_return > 0.001 else (2 if future_return < -0.001 else 0)
            
            # Reward: scale by return
            reward = abs(future_return) * 1000 if action != 0 else 0.1
            
            trajectories.append({
                'agent_obs': {k: torch.FloatTensor(v).unsqueeze(0) for k, v in obs.items()},
                'actions': torch.LongTensor([action]),
                'rewards': torch.FloatTensor([reward]),
                'global_states': torch.FloatTensor(global_state).unsqueeze(0)
            })
            
    print(f"[TRAIN] Harvested {len(trajectories)} data points. Calibrating HAPPO...")
    
    orchestrator = happo.HAPPOOrchestrator()
    orchestrator.sequential_update(trajectories)
    orchestrator.save("C:\\Sentinel_Project\\happo_weights.pth")
    print(f"[TRAIN] Calibration complete. Finalizing weights.")

if __name__ == "__main__":
    generate_training_data()
