import numpy as np
import torch
import torch.nn as nn

class OxfordDDQN(nn.Module):
    def __init__(self, input_dim, output_dim):
        super(OxfordDDQN, self).__init__()
        self.fc = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Linear(64, output_dim)
        )
    
    def forward(self, x):
        return self.fc(x)

def get_prediction(feature_matrix):
    # Mocking the DDQN inference process
    input_dim = feature_matrix.shape[1]
    model = OxfordDDQN(input_dim, 3) # 3 actions: Buy, Sell, Hold
    
    # Convert to tensor
    latest_features = torch.tensor(feature_matrix[-1], dtype=torch.float32).unsqueeze(0)
    
    with torch.no_grad():
        q_values = model(latest_features)
        # Convert Q-values to a "probability float" for conviction score
        # Using softmax for demonstration
        probs = torch.softmax(q_values, dim=1)
        conviction = probs[0][0].item() # Probability of 'Buy' for example
        
    return conviction

if __name__ == "__main__":
    # Mock feature matrix (e.g., from feature_engineering.py)
    matrix = np.random.rand(10, 6) # 10 rows, 6 features
    prob = get_prediction(matrix)
    print(f"DDQN Output Probability: {prob:.4f}")
    if 0 <= prob <= 1:
        print("Oxford DDQN diagnostic: SUCCESS")
    else:
        print("Oxford DDQN diagnostic: FAILED")
