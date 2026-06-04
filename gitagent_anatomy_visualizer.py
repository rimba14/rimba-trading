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

def plot_anatomy(json_path: str):
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    ticket_id = os.path.basename(json_path).split('_')[-1].replace('.json', '')
    traj = data.get('trajectory', [])
    
    if not traj:
        print(f"No trajectory data found for ticket {ticket_id}.")
        return

    # Extract time series
    steps = [t.get('step_bar_idx', i) for i, t in enumerate(traj)]
    prices = [t.get('price', 0.0) for t in traj]
    sls = [t.get('sl', 0.0) for t in traj]
    tps = [t.get('tp', 0.0) for t in traj]
    convictions = [t.get('conviction', 0.0) for t in traj]
    hmm_states = [t.get('hmm_state', 'UNKNOWN') for t in traj]
    
    # Extract SHAP data for Panel 4
    shap_keys = set()
    for t in traj:
        shap_keys.update(t.get('feature_shap_importance', {}).keys())
    shap_keys = sorted(list(shap_keys))
    
    shap_matrix = []
    for t in traj:
        shaps = t.get('feature_shap_importance', {})
        row = [shaps.get(k, 0.0) for k in shap_keys]
        shap_matrix.append(row)
    
    shap_matrix = np.array(shap_matrix).T if shap_matrix else np.zeros((1, len(steps)))

    # Set up the figure
    fig = plt.figure(figsize=(14, 12))
    gs = GridSpec(4, 1, height_ratios=[3, 1, 1, 2], hspace=0.3)
    fig.suptitle(f"SRE Forensic Anatomy: Ticket {ticket_id}", fontsize=16, fontweight='bold')

    # Panel 1: Price Action with TP/SL
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(steps, prices, color='blue', label='Price')
    
    # Handle SL and TP handling 0.0 values smoothly
    sl_array = np.array(sls)
    tp_array = np.array(tps)
    sl_array[sl_array == 0] = np.nan
    tp_array[tp_array == 0] = np.nan

    ax1.plot(steps, sl_array, color='red', linestyle='--', label='Stop Loss (Lower Barrier)')
    ax1.plot(steps, tp_array, color='green', linestyle='--', label='Take Profit (Upper Barrier)')
    
    # Entry and Exit markers
    if len(steps) > 0:
        ax1.scatter(steps[0], prices[0], color='black', marker='^', s=100, label='Entry')
        ax1.scatter(steps[-1], prices[-1], color='black', marker='v', s=100, label='Exit')
        
    ax1.set_ylabel("Price")
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.set_title("Panel 1: Triple Barrier & Price Action")

    # Panel 2: Regime-Shaded Heatmap (HMM State)
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    unique_states = list(set(hmm_states))
    state_to_idx = {s: i for i, s in enumerate(unique_states)}
    numeric_states = np.array([[state_to_idx[s] for s in hmm_states]])
    
    cmap = plt.get_cmap('Set3', len(unique_states))
    cax = ax2.imshow(numeric_states, aspect='auto', cmap=cmap, 
                     extent=[steps[0] if steps else 0, steps[-1] if steps else 1, 0, 1])
    ax2.set_yticks([])
    ax2.set_ylabel("HMM State")
    ax2.set_title("Panel 2: Regime State Heatmap")
    
    # Add state labels on the heatmap
    for idx, state in enumerate(hmm_states):
        if idx == 0 or state != hmm_states[idx-1]:
            ax2.text(steps[idx], 0.5, state, color='black', va='center', fontsize=8, rotation=90)

    # Panel 3: Conviction-line Plot
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax3.plot(steps, convictions, color='purple', linewidth=2)
    ax3.set_ylabel("Adj. Conviction")
    ax3.grid(True, alpha=0.3)
    ax3.set_title("Panel 3: Adjusted Conviction (P_blend x Activity Ratio)")
    ax3.set_ylim(0, max(max(convictions)+0.1 if convictions else 1.0, 1.0))

    # Panel 4: Feature Stability Heatmap
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    if shap_matrix.size > 0 and len(shap_keys) > 0:
        sns.heatmap(shap_matrix, yticklabels=shap_keys, cmap='coolwarm', center=0, 
                    ax=ax4, cbar=False, xticklabels=False)
    ax4.set_ylabel("Features")
    ax4.set_xlabel("Bar Step")
    ax4.set_title("Panel 4: Active SHAP Feature Stability")

    output_dir = os.path.dirname(json_path)
    output_path = os.path.join(output_dir, f"trade_anatomy_{ticket_id}.png")
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Visualized anatomy saved to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        plot_anatomy(sys.argv[1])
    else:
        print("Usage: python gitagent_anatomy_visualizer.py <path_to_json>")
