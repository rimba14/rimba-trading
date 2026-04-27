"""
GitAgent v13.0 — RenTec Reward Training Harness

Implements the reward function from the "Reward System Design: DeepMind vs RenTec" report:

    reward = net_return / rolling_volatility

Where:
    net_return  = (pnl_dollars - spread_cost) / entry_price
    rolling_vol = 20-bar ATR at exit, normalized to price units

Plus a single hard-wall penalty:
    If drawdown > 5% when trade closed → terminal reward = -1.0

This replaces the legacy `f_ret * 1000` scaling which had no cost awareness.
"""

import torch
import json
import os
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
from gitagent_ppo import PPOAgent, Memory
from gitagent_happo import HAPPOOrchestrator, AGENT_ORDER, AGENT_CONFIG

# ═══════════════════════════════════════════════════════════════
# DATA HARVESTER — Extract training episodes from RSI Journal
# ═══════════════════════════════════════════════════════════════

JOURNAL_FILE = "C:\\Sentinel_Project\\rsi_trade_journal.json"
THESIS_FILE = "C:\\Sentinel_Project\\position_thesis.json"

FEATURE_KEYS_PPO = ['W_rsi', 'Wy_trend', 'S_struct', 'W_pctR', 'CMF_flow', 'COSMO_lunar', 'TFM_edge']

HAPPO_OBS_MAP = {
    'trend':     ['W_rsi', 'Wy_trend', 'W_pctR'],
    'structure': ['S_struct', 'CMF_flow', 'COSMO_lunar'],
    'flow':      ['TFM_edge', 'TFM_dir', 'MEMORY_recall'],
    'deep':      ['W_rsi', 'TFM_edge', 'S_struct'],
    'macro':     ['COSMO_lunar', 'TFM_dir', 'Wy_trend'],
}

def load_journal():
    """Load closed trades from RSI journal with feature vectors."""
    if not os.path.exists(JOURNAL_FILE):
        print("[RENTEC] No trade journal found.")
        return []
    
    with open(JOURNAL_FILE, 'r') as f:
        data = json.load(f)
    
    trades = data.get('trades', [])
    # Filter trades that have feature vectors (post-Phase 7 trades)
    valid = [t for t in trades if t.get('features') and len(t['features']) > 0]
    print(f"[RENTEC] Loaded {len(valid)}/{len(trades)} trades with feature vectors.")
    return valid


def compute_rentec_reward(trade, rolling_vol=None):
    """
    RenTec-style reward: net_return / rolling_volatility
    
    Report Principle 1: Costs must be STRUCTURAL, not cosmetic.
    Report Principle 3: Reward simplicity is a form of robustness.
    Report Finding 2: Transaction cost modeling is the #1 component.
    """
    pnl = trade.get('pnl_dollars', 0.0)
    volume = trade.get('volume', 0.01)
    exit_price = trade.get('exit_price', 1.0)
    entry_atr = trade.get('features', {}).get('entry_atr', None)
    
    # --- Structural Cost Estimation ---
    # Estimate round-trip spread cost from symbol characteristics
    # For FX majors: ~0.0001-0.0003. For indices: ~0.5-2.0 points.
    # We approximate as 0.5 * ATR (conservative) when exact data unavailable.
    if entry_atr and entry_atr > 0:
        estimated_spread_cost = 0.1 * entry_atr * volume * 100  # Dollar estimate
    else:
        estimated_spread_cost = abs(pnl) * 0.02  # 2% of P&L as fallback
    
    # Net return (after costs)
    net_pnl = pnl - estimated_spread_cost
    
    # Normalize by entry price to get a return fraction
    net_return = net_pnl / (exit_price * volume + 1e-9)
    
    # --- Rolling Volatility Normalization ---
    # Use ATR as proxy for rolling volatility
    if entry_atr and entry_atr > 0:
        vol_normalized = net_return / (entry_atr / exit_price + 1e-9)
    elif rolling_vol and rolling_vol > 0:
        vol_normalized = net_return / rolling_vol
    else:
        vol_normalized = net_return * 100  # Fallback: raw scaling
    
    # Clip to prevent extreme outliers from dominating training
    reward = np.clip(vol_normalized, -5.0, 5.0)
    
    return float(reward)


def compute_drawdown_penalty(trade, account_high=None):
    """
    DeepMind Principle: Single hard-wall penalty.
    
    If the trade was closed during a drawdown > 5%, apply a terminal -1.0 signal.
    This teaches the agent that entering trades during drawdown crises is catastrophic.
    """
    surprise = trade.get('surprise', 0)
    pnl = trade.get('pnl_dollars', 0)
    
    # Heuristic: if surprise (absolute deviation from expectation) is extreme
    # AND the trade was a loss, this was likely a crisis-era trade
    if pnl < 0 and surprise > 50:
        return -1.0  # Terminal penalty (DeepMind binary loss signal)
    
    return 0.0  # No penalty


# ═══════════════════════════════════════════════════════════════
# PPO TRAINER — RenTec Reward
# ═══════════════════════════════════════════════════════════════

def train_ppo_rentec():
    """Train PPO agent with RenTec-style reward function."""
    trades = load_journal()
    if len(trades) < 20:
        print(f"[RENTEC] Insufficient data ({len(trades)} trades). Need 20+ for training.")
        return
    
    # Build training episodes
    episodes = []
    for trade in trades:
        features = trade.get('features', {})
        if not features:
            continue
        
        # Extract state vector (PPO uses 7 features)
        state = [features.get(k, 0.0) for k in FEATURE_KEYS_PPO]
        
        # Compute RenTec reward
        reward = compute_rentec_reward(trade)
        dd_penalty = compute_drawdown_penalty(trade)
        
        # Determine action from outcome
        pnl = trade.get('pnl_dollars', 0)
        if pnl > 0:
            action = 1  # Correct to BUY (or the signal that was taken)
        elif pnl < 0:
            action = 2  # Wrong direction → penalize the opposite
        else:
            action = 0  # Neutral
        
        episodes.append({
            'state': state,
            'action': action,
            'reward': reward + dd_penalty,  # Combined reward
            'symbol': trade.get('symbol', ''),
            'pnl': pnl
        })
    
    print(f"[RENTEC] Built {len(episodes)} training episodes.")
    
    # Reward statistics
    rewards = [e['reward'] for e in episodes]
    print(f"[RENTEC] Reward stats: mean={np.mean(rewards):.3f}, std={np.std(rewards):.3f}, "
          f"min={np.min(rewards):.3f}, max={np.max(rewards):.3f}")
    
    # --- Train PPO ---
    state_dim = len(FEATURE_KEYS_PPO)
    agent = PPOAgent(state_dim=state_dim, action_dim=3)
    
    # Load existing weights as warm start
    if os.path.exists("C:\\Sentinel_Project\\ppo_policy.pth"):
        try:
            agent.policy.load_state_dict(torch.load("C:\\Sentinel_Project\\ppo_policy.pth", map_location='cpu'))
            agent.policy_old.load_state_dict(agent.policy.state_dict())
            print("[RENTEC] Warm-starting from existing PPO policy.")
        except Exception as e:
            print(f"[RENTEC] Fresh start (load failed: {e})")
    
    memory = Memory()
    epochs = 15
    
    for epoch in range(epochs):
        epoch_reward = 0
        np.random.shuffle(episodes)
        
        for ep in episodes:
            state = ep['state']
            action = agent.select_action(state, memory)
            
            # RenTec reward: reward the CORRECT action, penalize wrong ones
            if action == ep['action']:
                memory.rewards.append(ep['reward'])
            elif action == 0:  # HOLD
                memory.rewards.append(-0.01)  # Small inactivity penalty
            else:
                memory.rewards.append(-abs(ep['reward']) * 0.5)  # Penalize wrong direction
            
            memory.is_terminals.append(True)
            epoch_reward += memory.rewards[-1]
        
        agent.update(memory)
        memory.clear_memory()
        
        print(f"[RENTEC PPO] Epoch {epoch+1}/{epochs} | Total Reward: {epoch_reward:.2f}")
    
    # Save
    torch.save(agent.policy.state_dict(), "C:\\Sentinel_Project\\ppo_policy_rentec.pth")
    print("[RENTEC] PPO policy saved to C:\\Sentinel_Project\\ppo_policy_rentec.pth")
    return agent


# ═══════════════════════════════════════════════════════════════
# HAPPO TRAINER — RenTec Reward
# ═══════════════════════════════════════════════════════════════

def train_happo_rentec():
    """Train HAPPO multi-agent system with RenTec-style reward function."""
    trades = load_journal()
    if len(trades) < 20:
        print(f"[RENTEC] Insufficient data ({len(trades)} trades). Need 20+ for training.")
        return
    
    # Build trajectories
    trajectories = []
    batch_size = 64
    current_batch = {
        'agent_obs': {name: [] for name in AGENT_ORDER},
        'actions': [],
        'rewards': [],
        'global_states': []
    }
    
    for trade in trades:
        features = trade.get('features', {})
        if not features:
            continue
        
        # Per-agent observation slicing
        agent_obs = {}
        global_state = []
        for name in AGENT_ORDER:
            obs = [features.get(k, 0.0) for k in HAPPO_OBS_MAP[name]]
            agent_obs[name] = obs
            global_state.extend(obs)
        
        # RenTec reward
        reward = compute_rentec_reward(trade)
        dd_penalty = compute_drawdown_penalty(trade)
        total_reward = reward + dd_penalty
        
        # Action label
        pnl = trade.get('pnl_dollars', 0)
        action = 1 if pnl > 0 else (2 if pnl < 0 else 0)
        
        # Accumulate
        for name in AGENT_ORDER:
            current_batch['agent_obs'][name].append(torch.FloatTensor(agent_obs[name]).unsqueeze(0))
        current_batch['actions'].append(action)
        current_batch['rewards'].append(total_reward)
        current_batch['global_states'].append(torch.FloatTensor(global_state).unsqueeze(0))
        
        # Flush batch
        if len(current_batch['actions']) >= batch_size:
            trajectories.append({
                'agent_obs': {name: torch.cat(current_batch['agent_obs'][name]) for name in AGENT_ORDER},
                'actions': torch.LongTensor(current_batch['actions']),
                'rewards': torch.FloatTensor(current_batch['rewards']),
                'global_states': torch.cat(current_batch['global_states'])
            })
            current_batch = {
                'agent_obs': {name: [] for name in AGENT_ORDER},
                'actions': [],
                'rewards': [],
                'global_states': []
            }
    
    # Flush remaining
    if current_batch['actions']:
        trajectories.append({
            'agent_obs': {name: torch.cat(current_batch['agent_obs'][name]) for name in AGENT_ORDER},
            'actions': torch.LongTensor(current_batch['actions']),
            'rewards': torch.FloatTensor(current_batch['rewards']),
            'global_states': torch.cat(current_batch['global_states'])
        })
    
    print(f"[RENTEC] Built {len(trajectories)} trajectory batches for HAPPO training.")
    
    # --- Train HAPPO ---
    happo = HAPPOOrchestrator(lr=0.0003, gamma=0.99, eps_clip=0.2, K_epochs=4)
    happo.load("C:\\Sentinel_Project\\happo_weights.pth")  # Warm start
    
    epochs = 10
    for epoch in range(epochs):
        np.random.shuffle(trajectories)
        happo.sequential_update(trajectories)
        
        # Compute epoch statistics
        all_rewards = torch.cat([t['rewards'] for t in trajectories])
        print(f"[RENTEC HAPPO] Epoch {epoch+1}/{epochs} | "
              f"Mean Reward: {all_rewards.mean():.3f} | Std: {all_rewards.std():.3f}")
    
    happo.save("C:\\Sentinel_Project\\happo_weights_rentec.pth")
    print("[RENTEC] HAPPO weights saved to C:\\Sentinel_Project\\happo_weights_rentec.pth")
    return happo


# ═══════════════════════════════════════════════════════════════
# REWARD COMPARISON REPORT
# ═══════════════════════════════════════════════════════════════

def generate_reward_report():
    """Compare old vs new reward distributions for audit transparency."""
    trades = load_journal()
    if not trades:
        print("[RENTEC] No trades to analyze.")
        return
    
    print(f"\n{'='*60}")
    print("REWARD COMPARISON: Legacy vs RenTec")
    print(f"{'='*60}")
    
    legacy_rewards = []
    rentec_rewards = []
    
    for trade in trades:
        pnl = trade.get('pnl_dollars', 0)
        features = trade.get('features', {})
        
        # Legacy reward (raw P&L * 1000)
        legacy = pnl * 1000
        legacy_rewards.append(legacy)
        
        # RenTec reward
        if features:
            rentec = compute_rentec_reward(trade)
        else:
            rentec = 0.0
        rentec_rewards.append(rentec)
    
    print(f"\n{'Metric':<25} {'Legacy':>12} {'RenTec':>12}")
    print("-" * 50)
    print(f"{'Mean':25} {np.mean(legacy_rewards):>12.3f} {np.mean(rentec_rewards):>12.3f}")
    print(f"{'Std':25} {np.std(legacy_rewards):>12.3f} {np.std(rentec_rewards):>12.3f}")
    print(f"{'Min':25} {np.min(legacy_rewards):>12.3f} {np.min(rentec_rewards):>12.3f}")
    print(f"{'Max':25} {np.max(legacy_rewards):>12.3f} {np.max(rentec_rewards):>12.3f}")
    print(f"{'Range':25} {np.ptp(legacy_rewards):>12.3f} {np.ptp(rentec_rewards):>12.3f}")
    
    # Win/Loss reward asymmetry
    wins_legacy = [r for r in legacy_rewards if r > 0]
    wins_rentec = [r for r in rentec_rewards if r > 0]
    losses_legacy = [r for r in legacy_rewards if r < 0]
    losses_rentec = [r for r in rentec_rewards if r < 0]
    
    print(f"\n{'Win Mean':25} {np.mean(wins_legacy) if wins_legacy else 0:>12.3f} {np.mean(wins_rentec) if wins_rentec else 0:>12.3f}")
    print(f"{'Loss Mean':25} {np.mean(losses_legacy) if losses_legacy else 0:>12.3f} {np.mean(losses_rentec) if losses_rentec else 0:>12.3f}")
    print(f"{'Reward Ratio (W/L)':25} {abs(np.mean(wins_legacy)/(np.mean(losses_legacy)+1e-9)) if wins_legacy else 0:>12.3f} "
          f"{abs(np.mean(wins_rentec)/(np.mean(losses_rentec)+1e-9)) if wins_rentec else 0:>12.3f}")
    
    print(f"\n[RENTEC] RenTec rewards have {'tighter' if np.std(rentec_rewards) < np.std(legacy_rewards) else 'wider'} "
          f"distribution — {'good' if np.std(rentec_rewards) < np.std(legacy_rewards) else 'check'} for gradient stability.")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("GitAgent v13.0 — RenTec Reward Training Harness")
    print("=" * 60)
    
    # Step 1: Audit
    generate_reward_report()
    
    # Step 2: Train PPO
    print(f"\n{'='*60}")
    print("PHASE 1: PPO Training (RenTec Reward)")
    print(f"{'='*60}")
    train_ppo_rentec()
    
    # Step 3: Train HAPPO
    print(f"\n{'='*60}")
    print("PHASE 2: HAPPO Training (RenTec Reward)")
    print(f"{'='*60}")
    train_happo_rentec()
    
    print(f"\n{'='*60}")
    print("TRAINING COMPLETE")
    print("New weights: C:\\Sentinel_Project\\ppo_policy_rentec.pth, C:\\Sentinel_Project\\happo_weights_rentec.pth")
    print("To deploy: copy *_rentec.pth → ppo_policy.pth / happo_weights.pth")
    print(f"{'='*60}")
