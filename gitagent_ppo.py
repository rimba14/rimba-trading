import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Categorical
import os
import numpy as np

class ActorCritic(nn.Module):
    def __init__(self, state_dim=16, action_dim=3, hidden_dim=64, lstm_units=128):
        super(ActorCritic, self).__init__()
        self.state_dim = state_dim
        self.lstm_units = lstm_units
        
        # 1. Input Projector: [16] -> [64]
        self.projector = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.Tanh()
        )
        
        # 2. LSTM Memory: seq_len=20 (handled in forward/training)
        self.lstm = nn.LSTM(hidden_dim, lstm_units, batch_first=True)
        
        # 3. Output Projector: [128] -> [64]
        self.post_lstm = nn.Sequential(
            nn.Linear(lstm_units, hidden_dim),
            nn.Tanh()
        )
        
        # 4. Heads
        self.action_layer = nn.Sequential(
            nn.Linear(hidden_dim, action_dim),
            nn.Softmax(dim=-1)
        )
        self.value_layer = nn.Linear(hidden_dim, 1)

    def forward(self, x, hidden=None):
        # x shape: [batch, seq_len, state_dim]
        batch_size = x.size(0)
        
        # project each step in sequence
        x = self.projector(x)
        
        # lstm pass
        # output: [batch, seq_len, lstm_units]
        x, hidden = self.lstm(x, hidden)
        
        # take last hidden state for decision
        x = x[:, -1, :] 
        
        x = self.post_lstm(x)
        action_probs = self.action_layer(x)
        state_value = self.value_layer(x)
        
        return action_probs, state_value, hidden

class PPOAgent:
    def __init__(self, state_dim=16, action_dim=3, lr=0.0003, seq_len=20, gamma=0.99, K_epochs=4, eps_clip=0.2):
        self.gamma = gamma
        self.eps_clip = eps_clip
        self.K_epochs = K_epochs
        self.seq_len = seq_len
        
        self.policy = ActorCritic(state_dim, action_dim)
        self.optimizer = optim.Adam(self.policy.parameters(), lr=lr)
        self.policy_old = ActorCritic(state_dim, action_dim)
        self.policy_old.load_state_dict(self.policy.state_dict())
        
        self.MseLoss = nn.MSELoss()
        
        # Buffer for online inference
        self.state_buffer = []

    def select_action(self, state, memory):
        # state is a single 16-dim vector
        self.state_buffer.append(state)
        if len(self.state_buffer) > self.seq_len:
            self.state_buffer.pop(0)
            
        # If buffer not full, pad with current state
        actual_buffer = self.state_buffer
        if len(actual_buffer) < self.seq_len:
            actual_buffer = [state] * (self.seq_len - len(actual_buffer)) + actual_buffer
            
        # Shape: [1, seq_len, state_dim]
        state_seq = torch.FloatTensor(np.array(actual_buffer)).unsqueeze(0)
        
        with torch.no_grad():
            probs, _, _ = self.policy_old(state_seq)
        
        dist = Categorical(probs)
        action = dist.sample()
        
        memory.states.append(state_seq)
        memory.actions.append(action)
        memory.logprobs.append(dist.log_prob(action))
        
        return action.item()

    def update(self, memory):
        rewards = []
        discounted_reward = 0
        for reward, is_terminal in zip(reversed(memory.rewards), reversed(memory.is_terminals)):
            if is_terminal:
                discounted_reward = 0
            discounted_reward = reward + (self.gamma * discounted_reward)
            rewards.insert(0, discounted_reward)
        
        rewards = torch.tensor(rewards, dtype=torch.float32)
        rewards = (rewards - rewards.mean()) / (rewards.std() + 1e-5)
        
        old_states = torch.cat(memory.states).detach() # [Batch, Seq, Dim]
        old_actions = torch.stack(memory.actions).detach()
        old_logprobs = torch.stack(memory.logprobs).detach()
        
        for _ in range(self.K_epochs):
            logprobs, state_values = self.evaluate(old_states, old_actions)
            ratios = torch.exp(logprobs - old_logprobs.detach())
            advantages = rewards - state_values.detach()   
            surr1 = ratios * advantages
            surr2 = torch.clamp(ratios, 1-self.eps_clip, 1+self.eps_clip) * advantages
            loss = -torch.min(surr1, surr2) + 0.5*self.MseLoss(state_values, rewards) - 0.01*self.entropy(logprobs)
            
            self.optimizer.zero_grad()
            loss.mean().backward()
            self.optimizer.step()
            
        self.policy_old.load_state_dict(self.policy.state_dict())

    def evaluate(self, state_seq, action):
        probs, state_value, _ = self.policy(state_seq)
        dist = Categorical(probs)
        action_logprobs = dist.log_prob(action)
        return action_logprobs, torch.squeeze(state_value)

    def entropy(self, logprobs):
        return -(torch.exp(logprobs) * logprobs).mean()

    def act(self, state):
        self.state_buffer.append(state)
        if len(self.state_buffer) > self.seq_len:
            self.state_buffer.pop(0)
        
        actual_buffer = self.state_buffer
        if len(actual_buffer) < self.seq_len:
            actual_buffer = [state] * (self.seq_len - len(actual_buffer)) + actual_buffer
            
        state_seq = torch.FloatTensor(np.array(actual_buffer)).unsqueeze(0)
        with torch.no_grad():
            probs, _, _ = self.policy_old(state_seq)
        return torch.argmax(probs).item(), probs[0].tolist()

class Memory:
    def __init__(self):
        self.actions = []
        self.states = []
        self.logprobs = []
        self.rewards = []
        self.is_terminals = []
 
    def clear_memory(self):
        self.actions.clear()
        self.states.clear()
        self.logprobs.clear()
        self.rewards.clear()
        self.is_terminals.clear()

# ─── SINGLETON CACHE (v9.8) ───
CACHED_AGENT = None

def get_ppo_action(state, model_path="C:\\Sentinel_Project\\ppo_policy.pth"):
    global CACHED_AGENT
    
    state_dim = len(state)
    
    # Lazy initialization or Re-init if state_dim changed (safety)
    if CACHED_AGENT is None or CACHED_AGENT.policy.state_dim != state_dim:
        print(f"[PPO] Initializing Agent with state_dim={state_dim}...")
        CACHED_AGENT = PPOAgent(state_dim=state_dim)
        if os.path.exists(model_path):
            try:
                CACHED_AGENT.policy_old.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
                print(f"[PPO] Weights loaded from {model_path}.")
            except Exception as e:
                print(f"[PPO] Load Error: {e}")
        # v11.4: JIT-trace policy_old projector for faster inference
        try:
            CACHED_AGENT.policy_old.eval()
            example = torch.zeros(1, 20, state_dim) # [Batch, Seq, Dim]
            # Since LSTM is stateful, we trace the feedforward projections
            # Actually, let's keep it simple and skip trace for now if it's too complex
            print(f"[PPO] LSTM enabled: skipping JIT trace for recurrent layers.")
        except Exception as e:
            print(f"[PPO] JIT trace failed: {e}, using eager mode.")
                
    return CACHED_AGENT.act(state)
