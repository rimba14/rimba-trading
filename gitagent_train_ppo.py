import torch
import pandas as pd
import numpy as np
from arcticdb import Arctic
from gitagent_ppo import PPOAgent, Memory
import random

def train_ppo():
    # 1. Load Data
    ac = Arctic("lmdb://C:\\sentinel_arctic")
    lib = ac.get_library("ppo_training")
    
    all_states = []
    for s in lib.list_symbols():
        df = lib.read(s).data
        # Cols: ['W', 'Wy', 'SMC', 'TRANS', 'RSI', 'CHG', 'reward']
        all_states.append(df)
        
    if not all_states:
        print("No training data found. Run data_prep first.")
        return
        
    df_train = pd.concat(all_states).sample(frac=1).reset_index(drop=True)
    print(f"Training on {len(df_train)} states.")

    # 2. Setup Agent
    state_dim = 7 # [W, Wy, SMC, TRANS, RSI, CHG, MICRO]
    action_dim = 3 # [Hold, Buy, Sell]
    agent = PPOAgent(state_dim, action_dim)
    memory = Memory()
    
    # 3. Training Loop
    epochs = 20
    batch_size = 500
    
    for epoch in range(epochs):
        epoch_reward = 0
        # Iterate through the data in chunks
        for i in range(0, len(df_train), batch_size):
            chunk = df_train.iloc[i : i + batch_size]
            
            for _, row in chunk.iterrows():
                state = [row['W'], row['Wy'], row['SMC'], row['TRANS'], row['RSI'], row['CHG'], row['MICRO']]
                action = agent.select_action(state, memory)
                
                # Reward Logic
                f_ret = row['reward']
                reward = 0
                if action == 1: # Buy
                    reward = f_ret * 1000 # Scale for gradient stability
                elif action == 2: # Sell
                    reward = -f_ret * 1000
                else: # Hold
                    reward = -0.01 # Small penalty for inactivity
                
                memory.rewards.append(reward)
                memory.is_terminals.append(True) # Every step is an independent choice for now
                epoch_reward += reward
                
            # Update Policy
            agent.update(memory)
            memory.clear_memory()
            
        print(f"Epoch {epoch+1} | Total Reward: {epoch_reward:.2f}")

    # 4. Save Policy
    torch.save(agent.policy.state_dict(), "C:\\Sentinel_Project\\ppo_policy.pth")
    print("Agent 14 Policy saved to C:\\Sentinel_Project\\ppo_policy.pth")

if __name__ == "__main__":
    train_ppo()
