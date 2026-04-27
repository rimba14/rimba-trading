import MetaTrader5 as mt5
import gitagent_happo as happo
import gitagent_lob as lob
import gitagent_microstructure as micro
import gitagent_transformer as trans
import gitagent_sigproc as sigproc

if not mt5.initialize():
    print("MT5 Init Failed")
    exit()

symbols = ['DJ30', 'NAS100', 'US500', 'XAUUSD', 'EURUSD', 'NVIDIA', 'AMAZON']

print("--- HAPPO LIVE RECOVERY SCAN ---")
best_sym = None
best_prob = 0
best_action = 0

for sym in symbols:
    df = sigproc.get_m15_dataframe(sym, 200)
    if df is None or len(df) < 50:
        continue
    
    trend_obs = happo.extract_trend_features(df)
    struct_obs = happo.extract_structure_features(df)
    flow_obs = happo.extract_flow_features(df)
    
    l1_imbalance = lob.get_l1_imbalance(sym)
    micro_liq = micro.measure_liquidity(df)
    t_score = trans.predict_transformer(df)
    deep_obs = [t_score, micro_liq, l1_imbalance]
    
    macro_obs = happo.extract_macro_features(df)
    
    agent_obs = {
        'trend': trend_obs,
        'structure': struct_obs,
        'flow': flow_obs,
        'deep': deep_obs,
        'macro': macro_obs
    }
    
    action, probs, contributions = happo.get_happo_action(agent_obs)
    action_str = "HOLD"
    prob = probs[0]
    if action == 1:
        action_str = "BUY"
        prob = probs[1]
    elif action == 2:
        action_str = "SELL"
        prob = probs[2]
        
    print(f"[{sym}] Signal: {action_str} | Confidence: {prob*100:.1f}% | Contrib: {contributions}")
    
    if action != 0 and prob > best_prob:
        best_prob = prob
        best_sym = sym
        best_action = action

print("\n--- RECOMMENDATION ---")
if best_sym:
    print(f"Top Recovery Candidate: {best_sym} -> {'BUY' if best_action == 1 else 'SELL'} ({best_prob*100:.1f}% confidence)")
else:
    print("No viable strong signals.")
