import re

config_path = r'C:\Sentinel_Project\sentinel_config.py'
loop_path = r'C:\Sentinel_Project\sentinel_slow_loop.py'

# 1. Update config
with open(config_path, 'r', encoding='utf-8') as f:
    config_content = f.read()

if 'STAGNANT_VARIANCE_THRESHOLD' not in config_content:
    with open(config_path, 'a', encoding='utf-8') as f:
        f.write('\n# v30.75 Consensus & Variance Safeguards\n')
        f.write('CONSENSUS_DIVERGENCE_THRESHOLD = 0.40\n')
        f.write('MIN_INFERENCE_AGENTS_REQUIRED  = 2\n')
        f.write('STAGNANT_VARIANCE_THRESHOLD    = 1e-7\n')

# 2. Update loop
with open(loop_path, 'r', encoding='utf-8') as f:
    loop_content = f.read()

# Zero-Variance Guard
old_zero = "if False: # pd.isna(price_variance) or price_variance == 0.0 or cumulative_volume == 0:"
new_zero = '''import sentinel_config
            if pd.isna(price_variance) or price_variance < getattr(sentinel_config, 'STAGNANT_VARIANCE_THRESHOLD', 1e-7) or cumulative_volume == 0:
                logging.warning(f"[SLOW_LOOP] [STAGNANT] Asset flatlining. Skipping cycle to protect matrix stability.")
                import os, json
                os.makedirs("shap_diagnostics", exist_ok=True)
                with open(f"shap_diagnostics/{symbol}_stagnant.json", "w") as f:
                    json.dump({"status": "STAGNANT", "variance": float(price_variance) if not pd.isna(price_variance) else 0.0, "volume": float(cumulative_volume)}, f)
                return {
                    "df_ml": None, "df_ta": None, "df_m15": df_m15, "df_h1": df_h1, "df_h4": None,
                    "swing_alpha": {}, "latest_swing": {}, "vrs": 1.0,
                    "wasserstein_state": "MARKET_STAGNANT", "wasser_prob": 1.0,
                    "label_probs": {"MARKET_STAGNANT": 1.0}, "data_quality_flag": "DEAD_MARKET",
                    "is_this_symbol_starved": is_this_symbol_starved, "atr": 0.0010, "m_state": m_state
                }'''

loop_content = loop_content.replace(old_zero, new_zero)

# Fix Dead Market bypass setting conviction to 0.0000
loop_content = loop_content.replace("_CYCLE_P_SCORES[symbol] = 0.500", "_CYCLE_P_SCORES[symbol] = 0.0000")

# Dynamic Quarantine
old_quar = '''for agent_name, agent_prob in list(active_scores.items()):
                if agent_prob > 0.95 or agent_prob < 0.05:
                    logging.warning(f"[{symbol}] [SOFTMAX_SATURATION_DETECTED] Agent '{agent_name}' outputted extreme/saturated confidence ({agent_prob:.4f}). Discarding from current cycle.")
                    del active_scores[agent_name]'''

new_quar = '''for agent_name, agent_prob in list(active_scores.items()):
                if agent_prob > 0.95 or agent_prob < 0.05:
                    logging.warning(f"[{symbol}] [SOFTMAX_SATURATION_DETECTED] Agent '{agent_name}' outputted extreme/saturated confidence ({agent_prob:.4f}). Discarding from current cycle.")
                    del active_scores[agent_name]
                elif agent_prob == 0.5000 or agent_prob is None or np.isnan(agent_prob):
                    logging.warning(f"[{symbol}] [DYNAMIC QUARANTINE] Agent '{agent_name}' returned 0.5000/NaN. Dropping from consensus.")
                    del active_scores[agent_name]'''
loop_content = loop_content.replace(old_quar, new_quar)

# Ensure no hard fallback to 0.5000 on consensus failure (using max conviction fallback instead)
old_consensus = '''if agree_on_direction:
                    logging.info(f"[{symbol}] CONSENSUS DIVERGENCE OVERRIDE: Models agree on directional sign. Allowing weighted blend P_blend={p_blend:.4f}.")
                else:
                    logging.warning(f"[{symbol}] CONSENSUS GATE BLOCKED: High model divergence detected. Falling back to soft weighted blend P_blend={p_blend:.4f}.")'''

new_consensus = '''if agree_on_direction:
                    logging.info(f"[{symbol}] CONSENSUS DIVERGENCE OVERRIDE: Models agree on directional sign. Allowing weighted blend P_blend={p_blend:.4f}.")
                else:
                    if len(valid_vals) > 0:
                        max_conviction_val = max(valid_vals)
                        min_conviction_val = min(valid_vals)
                        p_blend = max_conviction_val if max_conviction_val > 0.5 else min_conviction_val
                        logging.warning(f"[{symbol}] CONSENSUS GATE BLOCKED: Divergence > 0.40. Bypassing 0.5000 limit. Passing max raw conviction: P_blend={p_blend:.4f}.")
                    else:
                        logging.warning(f"[{symbol}] CONSENSUS GATE BLOCKED: No valid models. Falling back to 0.0000.")
                        p_blend = 0.0000'''

loop_content = loop_content.replace(old_consensus, new_consensus)

with open(loop_path, 'w', encoding='utf-8') as f:
    f.write(loop_content)

print("MIGRATION APPLIED SUCCESSFULLY.")
