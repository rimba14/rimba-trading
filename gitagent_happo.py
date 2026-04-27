"""
GitAgent v11.5 — HAPPO: TimesNet Perception Enabled
Multi-Agent RL Orchestrator with 79-dimensional learned state.
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Categorical
import numpy as np
import os

# ═══════════════════════════════════════════════════════════════
# AGENT DEFINITIONS — 79-Feature Distribution
# ═══════════════════════════════════════════════════════════════

AGENT_CONFIG = {
    'trend':     {'obs_dim': 19, 'desc': 'TN[0:16], Spread, MidRet, Vol'},
    'structure': {'obs_dim': 18, 'desc': 'TN[16:32], Q_Imb, Depth'},
    'flow':      {'obs_dim': 19, 'desc': 'TN[32:48], V_Imb, S_Vol, Toxicity'},
    'deep':      {'obs_dim': 18, 'desc': 'TN[48:64], AdvSelect, SpreadComp'},
    'macro':     {'obs_dim': 5,  'desc': 'Inv, PnL, Time, Regime, CompPress'},
    'wavelet':   {'obs_dim': 10, 'desc': 'Denoised, Approx, Det_L1-L2, Std_L1-L2, Scale, Pow, Shift'},
}

AGENT_ORDER = ['trend', 'structure', 'flow', 'deep', 'macro', 'wavelet']
GLOBAL_STATE_DIM = 89  # (79 + 10)
ACTION_DIM = 3  # HOLD=0, BUY=1, SELL=2

class HeterogeneousActor(nn.Module):
    def __init__(self, obs_dim, action_dim=ACTION_DIM, hidden_dim=64, lstm_units=128):
        super().__init__()
        self.projector = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.Tanh()
        )
        self.lstm = nn.LSTM(hidden_dim, lstm_units, batch_first=True)
        self.post_lstm = nn.Sequential(
            nn.Linear(lstm_units, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, action_dim),
            nn.Softmax(dim=-1)
        )
    
    def forward(self, obs_seq, hidden=None):
        x = self.projector(obs_seq)
        x, hidden = self.lstm(x, hidden)
        return self.post_lstm(x[:, -1, :]), hidden

class CentralizedCritic(nn.Module):
    def __init__(self, global_dim=GLOBAL_STATE_DIM, hidden_dim=64, lstm_units=128):
        super().__init__()
        self.projector = nn.Sequential(
            nn.Linear(global_dim, hidden_dim),
            nn.Tanh()
        )
        self.lstm = nn.LSTM(hidden_dim, lstm_units, batch_first=True)
        self.post_lstm = nn.Sequential(
            nn.Linear(lstm_units, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1)
        )
    
    def forward(self, global_seq, hidden=None):
        x = self.projector(global_seq)
        x, hidden = self.lstm(x, hidden)
        return self.post_lstm(x[:, -1, :]), hidden

class HAPPOOrchestrator:
    def __init__(self, lr=0.0003, gamma=0.99, eps_clip=0.2, K_epochs=4, seq_len=20):
        self.gamma = gamma
        self.eps_clip = eps_clip
        self.K_epochs = K_epochs
        self.seq_len = seq_len
        
        self.actors = {}
        self.actors_old = {}
        self.optimizers = {}
        
        for name in AGENT_ORDER:
            obs_dim = AGENT_CONFIG[name]['obs_dim']
            self.actors[name] = HeterogeneousActor(obs_dim)
            self.actors_old[name] = HeterogeneousActor(obs_dim)
            self.actors_old[name].load_state_dict(self.actors[name].state_dict())
            self.optimizers[name] = optim.Adam(self.actors[name].parameters(), lr=lr)
        
        self.critic = CentralizedCritic()
        self.critic_optimizer = optim.Adam(self.critic.parameters(), lr=lr)
        self.mse_loss = nn.MSELoss()
        self.obs_buffers = {name: [] for name in AGENT_ORDER}
    
    def act(self, agent_observations):
        all_probs = {}
        for name in AGENT_ORDER:
            self.obs_buffers[name].append(agent_observations[name])
            if len(self.obs_buffers[name]) > self.seq_len:
                self.obs_buffers[name].pop(0)
            
            actual_buf = self.obs_buffers[name]
            if len(actual_buf) < self.seq_len:
                actual_buf = [agent_observations[name]] * (self.seq_len - len(actual_buf)) + actual_buf
                
            obs_seq = torch.FloatTensor(np.array(actual_buf)).unsqueeze(0)
            probs, _ = self.actors_old[name](obs_seq)
            all_probs[name] = probs[0].tolist()
        
        fused_probs = torch.zeros(ACTION_DIM)
        agent_weights = {}
        for name in AGENT_ORDER:
            probs_t = torch.FloatTensor(all_probs[name])
            entropy = -(probs_t * torch.log(probs_t + 1e-8)).sum()
            confidence = max(0.1, 1.0 - entropy.item() / 1.099)
            agent_weights[name] = confidence
            fused_probs += probs_t * confidence
        
        fused_probs = fused_probs / (fused_probs.sum() + 1e-8)
        action = torch.argmax(fused_probs).item()
        total_weight = sum(agent_weights.values())
        contributions = {name: round(w / total_weight, 3) for name, w in agent_weights.items()}
        return action, fused_probs.tolist(), contributions

    def save(self, path="C:\\Sentinel_Project\\happo_weights.pth"):
        state = {'critic': self.critic.state_dict()}
        for name in AGENT_ORDER:
            state[f'actor_{name}'] = self.actors[name].state_dict()
        torch.save(state, path)

    def load(self, path="C:\\Sentinel_Project\\happo_weights.pth"):
        if not os.path.exists(path): return False
        try:
            state = torch.load(path, map_location=torch.device('cpu'))
            if 'actor_trend' not in state: return False # Legacy mismatch
            self.critic.load_state_dict(state['critic'])
            for name in AGENT_ORDER:
                self.actors[name].load_state_dict(state[f'actor_{name}'])
                self.actors_old[name].load_state_dict(state[f'actor_{name}'])
            return True
        except: return False

CACHED_HAPPO = None

def get_happo_action(agent_observations, model_path="C:\\Sentinel_Project\\happo_weights.pth"):
    global CACHED_HAPPO
    if CACHED_HAPPO is None:
        CACHED_HAPPO = HAPPOOrchestrator()
        CACHED_HAPPO.load(model_path)
    return CACHED_HAPPO.act(agent_observations)
