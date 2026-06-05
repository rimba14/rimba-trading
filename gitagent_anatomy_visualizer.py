import os
import sys
import json
import logging
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import seaborn as sns

matplotlib.use('Agg')
logger = logging.getLogger("AnatomyVisualizer")

def load_anatomy_data(json_path: str):
    """Loads and validates anatomy JSON data."""
    if not os.path.exists(json_path):
        logger.error(f"Error: {json_path} not found.")
        return None

    with open(json_path, 'r') as f:
        return json.load(f)

def extract_trajectory_features(traj: list):
    """Extracts time series and SHAP matrix from trajectory data."""
    steps = [t.get('step_bar_idx', i) for i, t in enumerate(traj)]
    prices = [t.get('price', 0.0) for t in traj]
    sls = [t.get('sl', 0.0) for t in traj]
    tps = [t.get('tp', 0.0) for t in traj]
    convictions = [t.get('conviction', 0.0) for t in traj]
    hmm_states = [t.get('hmm_state', 'UNKNOWN') for t in traj]

    # Extract SHAP data
    shap_keys = set()
    for t in traj:
        shap_keys.update(t.get('feature_shap_importance', {}).keys())
    shap_keys = sorted(list(shap_keys))

    shap_matrix_list = []
    for t in traj:
        shaps = t.get('feature_shap_importance', {})
        row = [shaps.get(k, 0.0) for k in shap_keys]
        shap_matrix_list.append(row)

    if shap_matrix_list:
        shap_matrix = np.array(shap_matrix_list).T
    else:
        shap_matrix = np.zeros((1, len(steps)))

    return {
        "steps": steps,
        "prices": prices,
        "sls": sls,
        "tps": tps,
        "convictions": convictions,
        "hmm_states": hmm_states,
        "shap_keys": shap_keys,
        "shap_matrix": shap_matrix
    }

def plot_price_action(ax, steps, prices, sls, tps):
    """Panel 1: Price Action with TP/SL."""
    ax.plot(steps, prices, color='blue', label='Price')
    
    sl_array = np.array(sls)
    tp_array = np.array(tps)
    sl_array[sl_array == 0] = np.nan
    tp_array[tp_array == 0] = np.nan

    ax.plot(steps, sl_array, color='red', linestyle='--', label='Stop Loss (Lower Barrier)')
    ax.plot(steps, tp_array, color='green', linestyle='--', label='Take Profit (Upper Barrier)')
    
    if len(steps) > 0:
        ax.scatter(steps[0], prices[0], color='black', marker='^', s=100, label='Entry')
        ax.scatter(steps[-1], prices[-1], color='black', marker='v', s=100, label='Exit')
        
    ax.set_ylabel("Price")
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    ax.set_title("Panel 1: Triple Barrier & Price Action")

def plot_regime_heatmap(ax, steps, hmm_states):
    """Panel 2: Regime-Shaded Heatmap (HMM State)."""
    unique_states = sorted(list(set(hmm_states)))
    state_to_idx = {s: i for i, s in enumerate(unique_states)}
    numeric_states = np.array([[state_to_idx[s] for s in hmm_states]])
    
    cmap = plt.get_cmap('Set3', len(unique_states))
    ax.imshow(numeric_states, aspect='auto', cmap=cmap,
              extent=[steps[0] if steps else 0, steps[-1] if steps else 1, 0, 1])
    ax.set_yticks([])
    ax.set_ylabel("HMM State")
    ax.set_title("Panel 2: Regime State Heatmap")
    
    for idx, state in enumerate(hmm_states):
        if idx == 0 or state != hmm_states[idx-1]:
            ax.text(steps[idx], 0.5, state, color='black', va='center', fontsize=8, rotation=90)

def plot_conviction_line(ax, steps, convictions):
    """Panel 3: Conviction-line Plot."""
    ax.plot(steps, convictions, color='purple', linewidth=2)
    ax.set_ylabel("Adj. Conviction")
    ax.grid(True, alpha=0.3)
    ax.set_title("Panel 3: Adjusted Conviction (P_blend x Activity Ratio)")
    if convictions:
        ax.set_ylim(0, max(max(convictions) + 0.1, 1.0))
    else:
        ax.set_ylim(0, 1.0)

def plot_feature_stability(ax, shap_matrix, shap_keys):
    """Panel 4: Feature Stability Heatmap."""
    if shap_matrix.size > 0 and len(shap_keys) > 0:
        sns.heatmap(shap_matrix, yticklabels=shap_keys, cmap='coolwarm', center=0, 
                    ax=ax, cbar=False, xticklabels=False)
    ax.set_ylabel("Features")
    ax.set_xlabel("Bar Step")
    ax.set_title("Panel 4: Active SHAP Feature Stability")

def plot_anatomy(json_path: str):
    data = load_anatomy_data(json_path)
    if not data:
        return

    ticket_id = os.path.basename(json_path).split('_')[-1].replace('.json', '')
    traj = data.get('trajectory', [])

    if not traj:
        logger.warning(f"No trajectory data found for ticket {ticket_id}.")
        return

    features = extract_trajectory_features(traj)
    steps = features['steps']

    # Set up the figure
    fig = plt.figure(figsize=(14, 12))
    gs = GridSpec(4, 1, height_ratios=[3, 1, 1, 2], hspace=0.3)
    fig.suptitle(f"SRE Forensic Anatomy: Ticket {ticket_id}", fontsize=16, fontweight='bold')

    # Panel 1
    ax1 = fig.add_subplot(gs[0])
    plot_price_action(ax1, steps, features['prices'], features['sls'], features['tps'])

    # Panel 2
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    plot_regime_heatmap(ax2, steps, features['hmm_states'])

    # Panel 3
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    plot_conviction_line(ax3, steps, features['convictions'])

    # Panel 4
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    plot_feature_stability(ax4, features['shap_matrix'], features['shap_keys'])

    output_dir = os.path.dirname(json_path)
    output_path = os.path.join(output_dir, f"trade_anatomy_{ticket_id}.png")
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(output_path, dpi=150)
    plt.close()
    logger.info(f"Visualized anatomy saved to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        plot_anatomy(sys.argv[1])
    else:
        print("Usage: python gitagent_anatomy_visualizer.py <path_to_json>")
