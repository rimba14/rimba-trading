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

def _extract_trajectory_data(json_path: str):
    """
    Loads JSON data and extracts trajectory information for visualization.
    """
    if not os.path.exists(json_path):
        logger.error(f"Error: {json_path} not found.")
        return None

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {json_path}: {e}")
        return None

    ticket_id = os.path.basename(json_path).split('_')[-1].replace('.json', '')
    traj = data.get('trajectory', [])
    
    if not traj:
        logger.warning(f"No trajectory data found for ticket {ticket_id}.")
        return None

    # Extract time series
    steps = [t.get('step_bar_idx', i) for i, t in enumerate(traj)]
    prices = [t.get('price', 0.0) for t in traj]
    sls = [t.get('sl', 0.0) for t in traj]
    tps = [t.get('tp', 0.0) for t in traj]
    convictions = [t.get('conviction', 0.0) for t in traj]
    hmm_states = [t.get('hmm_state', 'UNKNOWN') for t in traj]
    
    # Handle SL and TP handling 0.0 values smoothly
    sl_array = np.array(sls)
    tp_array = np.array(tps)
    sl_array[sl_array == 0] = np.nan
    tp_array[tp_array == 0] = np.nan

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

    return {
        "ticket_id": ticket_id,
        "steps": steps,
        "prices": prices,
        "sl_array": sl_array,
        "tp_array": tp_array,
        "convictions": convictions,
        "hmm_states": hmm_states,
        "shap_matrix": shap_matrix,
        "shap_keys": shap_keys
    }

def _plot_price_panel(ax, steps, prices, sl_array, tp_array):
    """Plots Price Action with TP/SL barriers."""
    ax.plot(steps, prices, color='blue', label='Price')
    ax.plot(steps, sl_array, color='red', linestyle='--', label='Stop Loss (Lower Barrier)')
    ax.plot(steps, tp_array, color='green', linestyle='--', label='Take Profit (Upper Barrier)')
    
    # Entry and Exit markers
    if len(steps) > 0:
        ax.scatter(steps[0], prices[0], color='black', marker='^', s=100, label='Entry')
        ax.scatter(steps[-1], prices[-1], color='black', marker='v', s=100, label='Exit')
        
    ax.set_ylabel("Price")
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    ax.set_title("Panel 1: Triple Barrier & Price Action")

def _plot_regime_panel(ax, steps, hmm_states):
    """Plots Regime-Shaded Heatmap (HMM State)."""
    unique_states = list(set(hmm_states))
    state_to_idx = {s: i for i, s in enumerate(unique_states)}
    numeric_states = np.array([[state_to_idx[s] for s in hmm_states]])
    
    cmap = plt.get_cmap('Set3', len(unique_states))
    ax.imshow(numeric_states, aspect='auto', cmap=cmap,
              extent=[steps[0] if steps else 0, steps[-1] if steps else 1, 0, 1])
    ax.set_yticks([])
    ax.set_ylabel("HMM State")
    ax.set_title("Panel 2: Regime State Heatmap")
    
    # Add state labels on the heatmap
    for idx, state in enumerate(hmm_states):
        if idx == 0 or state != hmm_states[idx-1]:
            ax.text(steps[idx], 0.5, state, color='black', va='center', fontsize=8, rotation=90)

def _plot_conviction_panel(ax, steps, convictions):
    """Plots Conviction-line Plot."""
    ax.plot(steps, convictions, color='purple', linewidth=2)
    ax.set_ylabel("Adj. Conviction")
    ax.grid(True, alpha=0.3)
    ax.set_title("Panel 3: Adjusted Conviction (P_blend x Activity Ratio)")
    if convictions:
        ax.set_ylim(0, max(max(convictions)+0.1, 1.0))
    else:
        ax.set_ylim(0, 1.0)

def _plot_feature_panel(ax, steps, shap_matrix, shap_keys):
    """Plots Feature Stability Heatmap."""
    if shap_matrix.size > 0 and len(shap_keys) > 0:
        sns.heatmap(shap_matrix, yticklabels=shap_keys, cmap='coolwarm', center=0,
                    ax=ax, cbar=False, xticklabels=False)
    ax.set_ylabel("Features")
    ax.set_xlabel("Bar Step")
    ax.set_title("Panel 4: Active SHAP Feature Stability")

def plot_anatomy(json_path: str):
    """
    Orchestrates the visualization of trade anatomy from a JSON file.
    """
    viz_data = _extract_trajectory_data(json_path)
    if viz_data is None:
        return

    ticket_id = viz_data["ticket_id"]
    steps = viz_data["steps"]

    # Set up the figure
    fig = plt.figure(figsize=(14, 12))
    gs = GridSpec(4, 1, height_ratios=[3, 1, 1, 2], hspace=0.3)
    fig.suptitle(f"SRE Forensic Anatomy: Ticket {ticket_id}", fontsize=16, fontweight='bold')

    # Panel 1: Price Action with TP/SL
    ax1 = fig.add_subplot(gs[0])
    _plot_price_panel(ax1, steps, viz_data["prices"], viz_data["sl_array"], viz_data["tp_array"])

    # Panel 2: Regime-Shaded Heatmap (HMM State)
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    _plot_regime_panel(ax2, steps, viz_data["hmm_states"])

    # Panel 3: Conviction-line Plot
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    _plot_conviction_panel(ax3, steps, viz_data["convictions"])

    # Panel 4: Feature Stability Heatmap
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    _plot_feature_panel(ax4, steps, viz_data["shap_matrix"], viz_data["shap_keys"])

    output_dir = os.path.dirname(json_path)
    output_path = os.path.join(output_dir, f"trade_anatomy_{ticket_id}.png")
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(output_path, dpi=150)
    plt.close()
    logger.info(f"Visualized anatomy saved to {output_path}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1:
        plot_anatomy(sys.argv[1])
    else:
        print("Usage: python gitagent_anatomy_visualizer.py <path_to_json>")
