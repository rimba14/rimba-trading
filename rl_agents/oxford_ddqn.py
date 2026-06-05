"""
rl_agents/oxford_ddqn.py - OXFORD DDQN STATISTICAL ARBITRAGE AGENT (v23.0)
Constitution: Deep Cognition Layer — operates as a PARALLEL signal to XGBoost.
MUST NOT override the Meta-Model. Output is a probability float fed to MixTS blending.

Architecture:
  - Double Deep Q-Network (DDQN) with target network stabilization.
  - State Space: 12-feature matrix (Microstructure Triad + FFT + FracDiff + 
                  CrossImpact + NLP Sentiment + Ensemble Alpha + CS Rank).
  - Action Space: 3 discrete actions — [Z_TIGHTEN (-1), HOLD (0), Z_WIDEN (+1)]
                  representing dynamic Z-score threshold adjustments for stat-arb.
  - Output: DDQN probability float [0, 1] consumed by gitagent_mixts.py Thompson Sampling.
"""

import os
import logging
import numpy as np
from collections import deque
import random

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

logger = logging.getLogger("OxfordDDQN")

# ── Constants ──────────────────────────────────────────────────────────────────
STATE_DIM   = 20    # Feature vector dimension (v36.00: 8 Spatial + 12 Temporal)
ACTION_DIM  = 3     # Z_TIGHTEN=0, HOLD=1, Z_WIDEN=2
HIDDEN_DIM  = 128
LR          = 1e-4
GAMMA       = 0.99
TAU         = 0.005           # Soft target-network update coefficient
BUFFER_SIZE = 50_000
BATCH_SIZE  = 64
TARGET_UPDATE_FREQ = 100      # Hard update every N steps (fallback)
CHECKPOINT_PATH = os.path.join(os.path.dirname(__file__), "oxford_ddqn_weights.pt")


# ── Network Architecture ───────────────────────────────────────────────────────

class ChaityShoishobEncoder(nn.Module):
    """
    Multi-Time Scale Spatial-Temporal State Encoder
    Derived from Chaity & Shoishob (2025) HFT AI Architecture
    """
    def __init__(self, spatial_features=8, temporal_features=12, lstm_hidden=64):
        super(ChaityShoishobEncoder, self).__init__()
        
        # Stream A: High-Frequency Spatial Feature Extractor (CNN Path)
        self.spatial_cnn = nn.Sequential(
            nn.Conv1d(in_channels=1, out_channels=16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.BatchNorm1d(16),
            nn.Conv1d(in_channels=16, out_channels=32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Flatten()
        )
        
        self.cnn_flat_dim = 32 * spatial_features
        
        # Stream B: Low-Frequency Temporal Sequence Tracker (RNN Path)
        self.temporal_lstm = nn.LSTM(
            input_size=temporal_features,
            hidden_size=lstm_hidden,
            num_layers=2,
            batch_first=True,
            dropout=0.2
        )
        
        # Joint Integration Matrix
        self.fusion_layer = nn.Sequential(
            nn.Linear(self.cnn_flat_dim + lstm_hidden, 128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, 64)
        )

    def forward(self, x_spatial, x_temporal):
        x_s = x_spatial.unsqueeze(1)
        spatial_out = self.spatial_cnn(x_s)
        
        lstm_out, _ = self.temporal_lstm(x_temporal)
        temporal_out = lstm_out[:, -1, :]
        
        fused_context = torch.cat((spatial_out, temporal_out), dim=1)
        unified_latent_state = self.fusion_layer(fused_context)
        return unified_latent_state

class DuelingDDQNNet(nn.Module):
    """
    Dueling DDQN architecture for enhanced value estimation.
    Upgraded to Spatial-Temporal Dual-Stream (v36.00).
    """
    def __init__(self, state_dim: int = STATE_DIM, action_dim: int = ACTION_DIM, hidden: int = HIDDEN_DIM):
        super().__init__()
        self.encoder = ChaityShoishobEncoder(spatial_features=8, temporal_features=12, lstm_hidden=64)
        
        # Value stream
        self.value_head = nn.Sequential(
            nn.Linear(64, hidden // 2),
            nn.ReLU(),
            nn.Linear(hidden // 2, 1),
        )
        # Advantage stream
        self.advantage_head = nn.Sequential(
            nn.Linear(64, hidden // 2),
            nn.ReLU(),
            nn.Linear(hidden // 2, action_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Split flat input into spatial (first 8) and temporal (remaining 12)
        x_spatial = x[:, :8]
        x_temporal = x[:, 8:].unsqueeze(1) # Add seq dimension=1
        
        shared_out = self.encoder(x_spatial, x_temporal)
        value      = self.value_head(shared_out)
        advantage  = self.advantage_head(shared_out)
        q_values   = value + (advantage - advantage.mean(dim=-1, keepdim=True))
        return q_values


# ── Replay Buffer ──────────────────────────────────────────────────────────────

class ReplayBuffer:
    def __init__(self, max_size: int = BUFFER_SIZE):
        self.buffer = deque(maxlen=max_size)

    def push(self, state, action, reward, next_state, done):
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int):
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (
            torch.tensor(np.array(states), dtype=torch.float32),
            torch.tensor(actions, dtype=torch.long),
            torch.tensor(rewards, dtype=torch.float32),
            torch.tensor(np.array(next_states), dtype=torch.float32),
            torch.tensor(dones, dtype=torch.float32),
        )

    def __len__(self):
        return len(self.buffer)


# ── DDQN Agent ─────────────────────────────────────────────────────────────────

class OxfordDDQN:
    """
    Double DQN Statistical Arbitrage Agent (v23.0 Oxford Tier).

    Key DDQN corrections vs vanilla DQN:
      - Action selection: online network selects best action.
      - Value estimation: TARGET network evaluates that action.
      → Decouples selection from evaluation, eliminates maximization bias.

    Integration point:
      The agent outputs a probability float that gitagent_mixts.py
      blends alongside XGBoost conviction via Thompson Sampling.
      It does NOT replace or modify the Meta-Model output.
    """

    def __init__(
        self,
        state_dim: int = STATE_DIM,
        action_dim: int = ACTION_DIM,
        device: str = "cpu",
    ):
        self.state_dim  = state_dim
        self.action_dim = action_dim
        self.device     = torch.device(device)
        self.step_count = 0
        self.epsilon    = 1.0   # Exploration rate (decays during training)
        self.eps_min    = 0.05
        self.eps_decay  = 0.995

        # Online + Target networks (DDQN core)
        self.online_net = DuelingDDQNNet(state_dim, action_dim).to(self.device)
        self.target_net = DuelingDDQNNet(state_dim, action_dim).to(self.device)
        self.target_net.load_state_dict(self.online_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.Adam(self.online_net.parameters(), lr=LR)
        self.buffer    = ReplayBuffer(BUFFER_SIZE)

        # Load persisted weights if available
        if os.path.exists(CHECKPOINT_PATH):
            try:
                checkpoint = torch.load(CHECKPOINT_PATH, map_location=self.device, weights_only=True)
                self.online_net.load_state_dict(checkpoint["online"])
                self.target_net.load_state_dict(checkpoint["target"])
                self.epsilon = checkpoint.get("epsilon", self.eps_min)
                logger.info(f"[DDQN] Loaded checkpoint from {CHECKPOINT_PATH} (ε={self.epsilon:.3f})")
            except Exception as e:
                logger.warning(f"[DDQN] Could not load checkpoint: {e}. Starting fresh.")
        else:
            logger.info("[DDQN] No checkpoint found. Starting with random weights.")

    def select_action(self, state: np.ndarray) -> int:
        """ε-greedy action selection using the online network."""
        if random.random() < self.epsilon:
            return random.randint(0, self.action_dim - 1)
        with torch.no_grad():
            state_t = torch.tensor(state, dtype=torch.float32).unsqueeze(0).to(self.device)
            q_vals  = self.online_net(state_t)
            return int(q_vals.argmax(dim=-1).item())

    def infer_probability(self, feature_vector: np.ndarray) -> float:
        """
        Primary inference entry point for MixTS integration.

        Converts the DDQN Q-value distribution into a probability float [0, 1]
        representing directional conviction (analogous to XGBoost's P score):
          - Action 0 (Z_TIGHTEN): bearish signal → probability < 0.5
          - Action 1 (HOLD):      neutral         → probability ≈ 0.5
          - Action 2 (Z_WIDEN):   bullish signal  → probability > 0.5

        Returns:
            Float in [0, 1]. Consumed by MixTS as an independent model signal.
        """
        if len(feature_vector) != self.state_dim:
            logger.warning(
                f"[DDQN] Feature dim mismatch: expected {self.state_dim}, "
                f"got {len(feature_vector)}. Padding/truncating."
            )
            vec = np.zeros(self.state_dim, dtype=np.float32)
            n   = min(len(feature_vector), self.state_dim)
            vec[:n] = feature_vector[:n]
            feature_vector = vec

        # Replace NaN/Inf with neutral 0
        feature_vector = np.nan_to_num(feature_vector.astype(np.float32), nan=0.0, posinf=1.0, neginf=-1.0)

        with torch.no_grad():
            state_t = torch.tensor(feature_vector, dtype=torch.float32).unsqueeze(0).to(self.device)
            q_vals  = self.online_net(state_t).squeeze(0)
            # Softmax converts Q-values to an action probability distribution
            probs   = F.softmax(q_vals, dim=-1).cpu().numpy()

        # Map action distribution to a single scalar probability:
        # P = p(Z_WIDEN) + 0.5 * p(HOLD) → ranges [0, 1]
        ddqn_prob = float(probs[2] + 0.5 * probs[1])
        ddqn_prob = float(np.clip(ddqn_prob, 0.0, 1.0))

        logger.info(
            f"[DDQN] Q={[f'{q:.3f}' for q in q_vals.cpu().numpy()]} "
            f"| Probs={[f'{p:.3f}' for p in probs]} "
            f"| DDQN_P={ddqn_prob:.4f}"
        )
        return ddqn_prob

    def update(self, state, action, reward, next_state, done):
        """Store a transition and perform a DDQN update step if buffer is ready."""
        self.buffer.push(state, action, reward, next_state, done)
        self.step_count += 1

        if len(self.buffer) < BATCH_SIZE:
            return None

        loss = self._train_step()

        # Soft target-network update (Polyak averaging)
        for target_p, online_p in zip(self.target_net.parameters(), self.online_net.parameters()):
            target_p.data.copy_(TAU * online_p.data + (1.0 - TAU) * target_p.data)

        # Epsilon decay
        self.epsilon = max(self.eps_min, self.epsilon * self.eps_decay)

        return loss

    def _train_step(self) -> float:
        """Core DDQN Bellman update."""
        states, actions, rewards, next_states, dones = self.buffer.sample(BATCH_SIZE)
        states      = states.to(self.device)
        actions     = actions.to(self.device)
        rewards     = rewards.to(self.device)
        next_states = next_states.to(self.device)
        dones       = dones.to(self.device)

        # Current Q-values from online network
        current_q = self.online_net(states).gather(1, actions.unsqueeze(1)).squeeze(1)

        with torch.no_grad():
            # DDQN: online selects action, target evaluates it
            next_actions = self.online_net(next_states).argmax(dim=-1, keepdim=True)
            next_q       = self.target_net(next_states).gather(1, next_actions).squeeze(1)
            target_q     = rewards + GAMMA * next_q * (1.0 - dones)

        loss = F.smooth_l1_loss(current_q, target_q)
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.online_net.parameters(), 10.0)
        self.optimizer.step()

        return float(loss.item())

    def save(self):
        """Persist weights to disk."""
        torch.save(
            {
                "online":  self.online_net.state_dict(),
                "target":  self.target_net.state_dict(),
                "epsilon": self.epsilon,
            },
            CHECKPOINT_PATH,
        )
        logger.info(f"[DDQN] Checkpoint saved → {CHECKPOINT_PATH}")


# ── Module-level singleton for MixTS integration ───────────────────────────────
_ddqn_agent: OxfordDDQN | None = None

def get_ddqn_agent() -> OxfordDDQN:
    """Lazy-initialised singleton. Thread-safe for read-only inference."""
    global _ddqn_agent
    if _ddqn_agent is None:
        _ddqn_agent = OxfordDDQN()
        logger.info("[DDQN] Oxford DDQN agent initialised (singleton).")
    return _ddqn_agent


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [DDQN] %(message)s")
    agent = OxfordDDQN()

    # Offline smoke test with random state
    dummy_state = np.random.randn(STATE_DIM).astype(np.float32)
    prob = agent.infer_probability(dummy_state)
    print(f"\n[OFFLINE TEST] DDQN_P = {prob:.4f}")
    assert 0.0 <= prob <= 1.0, "Output must be in [0, 1]"
    print("[OFFLINE TEST] PASSED ✓")
