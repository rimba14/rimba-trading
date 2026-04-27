import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np
from arcticdb import Arctic
from gitagent_transformer import TransformerEncoderModel
import os

class TradingDataset(Dataset):
    def __init__(self, data_df, seq_len=100, target_len=10):
        self.seq_len = seq_len
        # Normalize: log returns
        df_norm = data_df[['open', 'high', 'low', 'close', 'tick_volume']].pct_change().fillna(0)
        self.data = df_norm.values
        
        # Target: Return over the next 'target_len' bars
        # Shift close prices back
        future_returns = (data_df['close'].shift(-target_len) - data_df['close']) / data_df['close']
        self.targets = future_returns.fillna(0).values
        
        self.valid_indices = range(seq_len, len(self.data) - target_len)

    def __len__(self):
        return len(self.valid_indices)

    def __getitem__(self, idx):
        start = self.valid_indices[idx] - self.seq_len
        end = self.valid_indices[idx]
        x = self.data[start:end]
        y = self.targets[end]
        return torch.tensor(x, dtype=torch.float), torch.tensor([y], dtype=torch.float)

def train_model():
    # 1. Load Data from ArcticDB
    ac = Arctic("lmdb://C:\\sentinel_arctic")
    lib = ac.get_library("trading_data")
    
    # Concatenate data from multiple symbols for better generalization
    all_dfs = []
    for sym in ["EURUSD_M1", "GBPUSD_M1", "BTCUSD_M1", "USDJPY_M1"]:
        try:
            df = lib.read(sym).data
            if not df.empty:
                all_dfs.append(df)
        except:
            continue
            
    if not all_dfs:
        print("No data found in ArcticDB. Run the feeder first!")
        return
        
    full_df = pd.concat(all_dfs)
    print(f"Loaded {len(full_df)} bars for training.")

    # 2. Setup Training
    dataset = TradingDataset(full_df)
    dataloader = DataLoader(dataset, batch_size=32, shuffle=True)
    
    model = TransformerEncoderModel()
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.0001)

    # 3. Training Loop
    model.train()
    print("Starting Calibration...")
    for epoch in range(5):
        total_loss = 0
        for x, y in dataloader:
            # x shape needs to be (seq_len, batch, input_dim) for nn.Transformer
            x = x.transpose(0, 1)
            
            optimizer.zero_grad()
            output = model(x)
            loss = criterion(output, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        
        print(f"Epoch {epoch+1} | Loss: {total_loss / len(dataloader):.6f}")

    # 4. Save Weights
    torch.save(model.state_dict(), "C:\\Sentinel_Project\\transformer_weights.pth")
    print("Weights saved to C:\\Sentinel_Project\\transformer_weights.pth")

if __name__ == "__main__":
    train_model()
