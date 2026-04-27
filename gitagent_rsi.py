import os
import json
import time
import math
import random
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import gitagent_synthesis as syn
import gitagent_mixts as mixts
import gitagent_utils as utils

# =============================================================================
# GITAGENT PHASE 3: EVOLUTIONARY INTELLIGENCE ENGINE
# =============================================================================

THESIS_FILE = "C:\\Sentinel_Project\\position_thesis.json"
JOURNAL_FILE = "C:\\Sentinel_Project\\rsi_trade_journal.json"
WEIGHTS_FILE = "C:\\Sentinel_Project\\rsi_weights.json"
DATASET_FILE = "C:\\Sentinel_Project\\rsi_trade_dataset.json"

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception: pass
    return default

def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def connect_mt5():
    if not mt5.initialize(): return False
    return True

def get_base_weights():
    vix = utils.live_vix()
    return get_dynamic_base_weights(vix)

def get_dynamic_base_weights(vix):
    """
    Phase 63: Dynamic Bayesian conviction based on market stress.
    Calm (<18): Favor RSI and Cosmic Mean Reversion.
    Crisis (>25): Favor Whales (Structure) and LLM News Sentiment.
    """
    w = {
        'W_rsi': 1.2, 'Wy_trend': 1.1, 'S_struct': 1.8,
        'MB_rpb': 1.4, 'LLM_nlp': 1.5, 'WHL_vol': 1.4, 'SEN_sent': 0.5,
        '_rbf_buy': 3.0, '_rbf_sell': -3.0,
        'COSMO_geoAp': 0.4, 'COSMO_lunar': 0.3, 'COSMO_align': 0.5
    }
    
    if vix < 18:
        # Range/Mean-reverting regime
        w['W_rsi'] = 1.6 # +0.4 boost to RSI
        w['COSMO_align'] = 0.8 
    elif vix > 25:
        # High volatility / Panic regime
        w['S_struct'] = 2.8   # Whales provide safety in structural levels
        w['LLM_nlp'] = 2.2    # News sentiment is critical in crisis
        w['Wy_trend'] = 1.8   # High momentum conviction
        w['W_rsi'] = 0.4      # Avoid mean-reversion during trending panic
        
    return w

def process_closed_trades():
    if not connect_mt5(): return

    thesis_data = load_json(THESIS_FILE, {})
    if not thesis_data: return
        
    journal_data = load_json(JOURNAL_FILE, {"version": "3.0", "trades": []})
    rsi_state = load_json(WEIGHTS_FILE, {})
    if not rsi_state:
        rsi_state = {
            "production_weights": get_base_weights(),
            "total_trades": 0,
            "last_tournament_trade": 0,
            "last_evo_trade": 0,
            "model_version": 1,
            "meta_mode": "EXPLORE",
            "evo_history": []
        }
    
    # Force legacy key presence
    if "total_trades" not in rsi_state: rsi_state["total_trades"] = 0
    if "production_weights" not in rsi_state: rsi_state["production_weights"] = get_base_weights()

    from_date = datetime.now() - timedelta(days=5)
    to_date = datetime.now() + timedelta(days=1)
    deals = mt5.history_deals_get(from_date, to_date)
    if not deals: return

    journaled_ids = {str(t["trade_id"]) for t in journal_data["trades"]}
    exit_deals = [d for d in deals if d.entry == 1 and str(d.position_id) in thesis_data and str(d.position_id) not in journaled_ids]
    
    if not exit_deals: return

    print(f"\n{'='*60}")
    print(f"[*] GITAGENT PHASE 3 EVO ENGINE - EVALUATING {len(exit_deals)} TRADES")
    print(f"{'='*60}")
    
    mixts_agent = mixts.MixTSAgent()
    
    for deal in exit_deals:
        # Reconstruct exactly what we do for fueling the dataset
        trade_id = str(deal.position_id)
        entry_snap = thesis_data.get(trade_id, {})
        features = entry_snap.get("entry_features", {})
        mono_score = entry_snap.get("monolithic_score", 0.0)
        
        # ─── v12.6 FRONTIER FORENSIC LOOP ───
        try:
            from gitagent_forensic import ForensicEngine
            fe = ForensicEngine()
            critique = fe.audit_deal(deal, entry_snap)
        except Exception as e:
            critique = f"Forensic loop error: {e}"
        
        outcome = 1 if deal.profit > 0 else -1
        predicted_dir = 1.0 if mono_score > 0 else -1.0
        surprise = abs(abs(mono_score * deal.volume * 1.5) - deal.profit) / max(0.1, abs(mono_score * deal.volume * 1.5))
        
        record = {
            "trade_id": trade_id,
            "symbol": deal.symbol,
            "outcome": outcome,
            "features": features,
            "monolithic_score": mono_score,
            "pnl": deal.profit,
            "quality": deal.profit / 5.0, # Approximate risk ratio
            "surprise": surprise,
            "fired_skill_id": features.get("_fired_skill")
        }
        journal_data["trades"].append(record)
        rsi_state["total_trades"] += 1
        
        # ─── PHASE 14: MixTS POSTERIOR UPDATE ───
        try:
            x_vec = [features.get(k, 0.0) for k in mixts.FEATURE_KEYS]
            # Replace None with 0.0
            x_vec = [v if v is not None else 0.0 for v in x_vec]
            mixts_agent.update_posteriors(x_vec, deal.profit)
        except Exception as e:
            print(f"  [MIXTS] Update Error: {e}")
            
        print(f"  -> Added trade {trade_id} [{deal.symbol}] | PnL: ${deal.profit:.2f}")
        
        # ─── PHASE 4: HERMES SKILL SYSTEM UPDATE ───
        try:
            import gitagent_skills as skills
            skills.update_skills(record)
            skills.extract_skill(record)
        except Exception as e:
            pass

    save_json(JOURNAL_FILE, journal_data)
    
    # Meta-Controller 
    update_meta_state(rsi_state, journal_data)
    
    # System A Virtual Resolution
    evaluate_virtual_trades()

    # EVOLUTIONARY TRIGGERS
    trades_since_tourn = rsi_state["total_trades"] - rsi_state.get("last_tournament_trade", 0)
    if trades_since_tourn >= 50:
        run_tournament(rsi_state, journal_data)
        rsi_state["last_tournament_trade"] = rsi_state["total_trades"]
        
    trades_since_evo = rsi_state["total_trades"] - rsi_state.get("last_evo_trade", 0)
    if trades_since_evo >= 200:
        run_architectural_evolution(rsi_state, journal_data)
        rsi_state["last_evo_trade"] = rsi_state["total_trades"]

    save_json(WEIGHTS_FILE, rsi_state)
    mt5.shutdown()

# -----------------------------------------------------------------------------
# STEP 3: TOURNAMENT SELECTION
# -----------------------------------------------------------------------------
def get_combined_dataset(journal_data):
    # Combine backfilled dataset and live journal dataset
    fuel = load_json(DATASET_FILE, {"trades": []})
    dataset = fuel.get("trades", [])
    
    # Format journal trades to match
    live = []
    for t in journal_data.get("trades", []):
        outcome = t.get("outcome", 1)
        if isinstance(outcome, str): outcome = 1 if outcome == "WIN" else -1
        pnl = t.get("pnl", t.get("pnl_dollars", 0.0))
        qual = t.get("quality", pnl / 5.0)
        live.append({
            "features": t.get("features", {}),
            "outcome": outcome,
            "quality": qual,
            "pnl": pnl
        })
    return dataset + live

def calculate_hit_rates(dataset):
    hits = {}
    totals = {}
    for t in dataset:
        for k, v in t.get("features", {}).items():
            if k not in hits: hits[k] = 0; totals[k] = 0
            if (v > 0 and t["outcome"] > 0) or (v < 0 and t["outcome"] < 0):
                hits[k] += 1
            totals[k] += 1
    return {k: hits[k]/max(1, totals[k]) for k in hits}

def score_dataset(config_weights, interaction_adj, dataset, name):
    sharpe_returns = []
    wins = 0; losses = 0
    gross_wins = 0.0; gross_loss = 0.0
    avoided_losses = 0; missed_wins = 0
    
    int_thresh = interaction_adj.get("threshold", 0.2)
    int_wt = interaction_adj.get("weight", 0.0)
    
    for t in dataset:
        feats = t["features"]
        kernel = syn.kernel_transform(feats, interaction_threshold=int_thresh)
        
        # Apply special mutant interaction weights
        if int_wt > 0:
            for k in kernel:
                if 'x' in k and 'W' not in k: # It's an interaction
                    config_weights[k] = max(0.01, min(config_weights.get(k, 1.0) * int_wt, 5.0))
                    
        score = syn.monolithic_score(kernel, bayes_weights=config_weights)
        shadow_dir = 1.0 if score > 0 else -1.0
        
        if abs(score) < 5.0: # Shadow said HOLD
            if t["outcome"] == -1: avoided_losses += 1
            else: missed_wins += 1
            continue
            
        # Simulated returns
        pnl_val = t.get("pnl", t.get("pnl_dollars", 0.0))
        p_outcome = t.get("outcome", 1)
        pnl_sim = abs(pnl_val) if (shadow_dir > 0 and p_outcome > 0) or (shadow_dir < 0 and p_outcome < 0) else -abs(pnl_val)
        sharpe_returns.append(pnl_sim)
        
        if pnl_sim > 0:
            wins += 1
            gross_wins += pnl_sim
        else:
            losses += 1
            gross_loss += abs(pnl_sim)
            
    win_rate = wins / max(1, (wins + losses))
    pf = gross_wins / max(1e-9, gross_loss)
    
    mean_r = np.mean(sharpe_returns) if sharpe_returns else 0
    std_r = np.std(sharpe_returns) + 1e-9 if sharpe_returns else 1.0
    sharpe = (mean_r / std_r) * np.sqrt(max(1, len(sharpe_returns)))
    
    fitness = (sharpe * 0.4) + (win_rate * 0.3) + (pf * 0.2) + ((avoided_losses - missed_wins) * 0.1)
    
    return {
        "name": name,
        "weights": config_weights,
        "fitness": fitness,
        "sharpe": sharpe,
        "win_rate": win_rate
    }

def run_tournament(rsi_state, journal_data):
    print("\n[!!!] EVO LAYER: RUNNING GENETIC TOURNAMENT [!!!]")
    dataset = get_combined_dataset(journal_data)
    if not dataset: return
    
    prod = rsi_state.get("production_weights", get_base_weights())
    hit_rates = calculate_hit_rates(dataset)
    
    # Generate Mutants
    # 0. CONTROL
    configs = []
    configs.append(("CONTROL", prod.copy(), {}))
    
    # 1. MUTANT A: Perturbation
    mut_a = {k: max(0.01, min(v * (1 + random.uniform(-0.15, 0.15)), 5.0)) for k, v in prod.items()}
    configs.append(("MUTANT_A_PERTURB", mut_a, {}))
    
    # 2. MUTANT B: Amplifier
    mut_b = prod.copy()
    sorted_hits = sorted(hit_rates.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_hits) >= 6:
        for k, v in sorted_hits[:3]: mut_b[k] = max(0.01, min(v * 2.0, 5.0))
        for k, v in sorted_hits[-3:]: mut_b[k] = max(0.01, min(v * 0.5, 5.0))
    configs.append(("MUTANT_B_AMPLIFY", mut_b, {}))
    
    # 3. MUTANT C: Cosmic Boost
    mut_c = prod.copy()
    mut_c["COSMO_geoAp"] = 1.0
    mut_c["COSMO_lunar"] = 0.8
    mut_c["COSMO_align"] = 1.2
    configs.append(("MUTANT_C_COSMIC", mut_c, {}))
    
    # 4. MUTANT D: SMC Dominant
    mut_d = prod.copy()
    mut_d["S_struct"] = 3.0
    mut_d["W_rsi"] = 0.5
    mut_d["W_macd"] = 0.4
    configs.append(("MUTANT_D_SMC", mut_d, {}))
    
    # 5. MUTANT E: Kernel Ghost Hunter
    configs.append(("MUTANT_E_GHOST", prod.copy(), {"threshold": 0.1, "weight": 1.2}))
    
    results = []
    for name, wts, ints in configs:
        res = score_dataset(wts, ints, dataset, name)
        results.append(res)
        print(f"  -> {name:<20} | Fitness: {res['fitness']:.3f} | Sharpe: {res['sharpe']:.2f} | WR: {res['win_rate']:.1%}")
        
    results.sort(key=lambda x: x["fitness"], reverse=True)
    winner = results[0]
    control = next(r for r in results if r["name"] == "CONTROL")
    
    if winner["name"] != "CONTROL" and winner["fitness"] > control["fitness"] * 1.05:
        print(f"\n[+] TOURNAMENT: {winner['name']} DEPLOYED!")
        print(f"    Fitness: {control['fitness']:.3f} -> {winner['fitness']:.3f}")
        rsi_state["production_weights"] = winner["weights"].copy()
        rsi_state["model_version"] += 1
        rsi_state["evo_history"].append({
            "event": "TOURNAMENT",
            "winner": winner["name"],
            "improvement": winner["fitness"] / max(1e-9, control["fitness"]),
            "trade": rsi_state["total_trades"]
        })
    else:
        print(f"\n[=] TOURNAMENT: Control retained. Best challenger: {winner['name']}")

# -----------------------------------------------------------------------------
# STEP 4: ARCHITECTURAL EVOLUTION
# -----------------------------------------------------------------------------
def run_architectural_evolution(rsi_state, journal_data):
    print("\n[!!!] EVO LAYER: ARCHITECTURAL EVOLUTION (200 TRADES) [!!!]")
    dataset = get_combined_dataset(journal_data)
    hit_rates = calculate_hit_rates(dataset)
    
    prod = rsi_state.get("production_weights", {})
    new_prod = {}
    pruned = []
    stars = []
    
    # 4A: Feature Autopsy
    for k, v in prod.items():
        rate = hit_rates.get(k, 0.5)
        # Never prune RBF or active structures outright unless weight is absolutely zero
        if rate < 0.52 and abs(v) < 0.1 and not k.startswith("_rbf"):
            pruned.append((k, rate, v))
            continue
            
        new_prod[k] = v
        if rate > 0.65:
            new_prod[k] = max(v, 1.0) # Force minimum weight for stars
            stars.append((k, rate))
            
    for p in pruned:
        print(f"    [-] Removed dead feature: {p[0]} (HitRate: {p[1]:.1%}, Wt: {p[2]:.2f})")
    for s in stars:
        print(f"    [+] Promoted STAR feature: {s[0]} (HitRate: {s[1]:.1%})")
        
    # 4B: Feature Discovery is handled by gitagent_synthesis pushing new keys
    # into the kernel transform. Since we pass weights via get_base_weights,  
    # unknown keys naturally start at weight 1.0 in synthesis if unmapped. 
    # The tournament will tune them over time.
    
    rsi_state["production_weights"] = new_prod
    rsi_state["evo_history"].append({
        "event": "ARCHITECTURE",
        "pruned": len(pruned),
        "stars": len(stars),
        "trade": rsi_state["total_trades"]
    })

# -----------------------------------------------------------------------------
# SUBSYSTEMS: META-CONTROLLER AND PASSIVE OBSERVATION
# -----------------------------------------------------------------------------
def update_meta_state(rsi_state, journal):
    trades = journal.get("trades", [])
    if len(trades) < 20: return
    
    last_20 = trades[-20:]
    wins = sum(1 for t in last_20 if t["outcome"] > 0)
    win_rate_20 = wins / 20.0
    
    pnls = [t["pnl"] for t in last_20]
    pnl_mean = sum(pnls) / 20.0
    pnl_std = math.sqrt(sum((x - pnl_mean)**2 for x in pnls) / 20.0) + 1e-9
    sharpe_20 = (pnl_mean / pnl_std) * math.sqrt(20)
    
    cumulative = 0; peak = 0; dd_max = 0
    cons_losses = 0; max_cons = 0
    for t in trades[-50:]:
        cumulative += t["pnl"]
        if cumulative > peak: peak = cumulative
        dd = (peak - cumulative) / max(1.0, peak) if peak > 0 else 0
        if dd > dd_max: dd_max = dd
        
        if t["outcome"] < 0:
            cons_losses += 1
            if cons_losses > max_cons: max_cons = cons_losses
        else: cons_losses = 0

    current_mode = rsi_state.get("meta_mode", "EXPLORE")
    new_mode = current_mode
    if dd_max > 0.10 or max_cons >= 5: new_mode = "RECOVER"
    elif sharpe_20 > 1.5 and win_rate_20 > 0.55: new_mode = "EXPLOIT"
    elif sharpe_20 < 0.5: new_mode = "EXPLORE"
        
    rsi_state["meta_mode"] = new_mode
    if new_mode != current_mode:
        print(f"[*] META-CONTROLLER: Mode Shifted [{current_mode}] -> [{new_mode}]")

def evaluate_virtual_trades():
    # Passively clears System A virtual log out. 
    # With Phase 3, virtual trades don't update weights independently (gradient style),
    # but they can be injected into the dataset. To keep things pure for Phase 3, 
    # we just acknowledge their resolution.
    obs_file = "C:\\Sentinel_Project\\rsi_observation_journal.json"
    if not os.path.exists(obs_file): return
    
    with open(obs_file, "r") as f:
        obs_data = json.load(f)
        
    pending = [o for o in obs_data.get("observations", []) if o.get("status") == "PENDING"]
    if not pending: return
    
    now_utc = datetime.now(timezone.utc)
    evaluated = 0
    for obs in pending:
        obs_time = datetime.fromisoformat(obs["timestamp"])
        if (now_utc - obs_time).total_seconds() > 86400: # 24hr timeout
            obs["status"] = "TIMEOUT"
            evaluated += 1
            
    if evaluated > 0:
        with open(obs_file, "w") as f:
            json.dump(obs_data, f, indent=2)

if __name__ == "__main__":
    process_closed_trades()
    
    rsi_state = load_json(WEIGHTS_FILE, {})
    if "evo_history" not in rsi_state:
        rsi_state["evo_history"] = []
    journal_data = load_json(JOURNAL_FILE, {})
    if rsi_state and "last_tournament_trade" not in rsi_state:
        # First time Phase 3 trigger
        print("\n[*] Initializing Phase 3 Day 0 Genesis Tournament & Autopsy...")
        rsi_state["last_tournament_trade"] = rsi_state.get("total_trades", 0)
        rsi_state["last_evo_trade"] = rsi_state.get("total_trades", 0)
        run_tournament(rsi_state, journal_data)
        run_architectural_evolution(rsi_state, journal_data)
        save_json(WEIGHTS_FILE, rsi_state)
