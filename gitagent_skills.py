import json
import math
import os
import uuid
from datetime import datetime, timezone

SKILLS_FILE = "C:\\Sentinel_Project\\rsi_skills.json"

def load_json(filepath, default):
    if not os.path.exists(filepath): return default
    try:
        with open(filepath, "r") as f: return json.load(f)
    except: return default

def save_json(filepath, data):
    with open(filepath, "w") as f: json.dump(data, f, indent=2)

# =============================================================================
# TRADE MEMORY SEARCH (k-NN)
# =============================================================================
def search_trade_memory(current_features, journal_data, k=5):
    """
    Search historical trades for the `k` closest feature vectors.
    Returns: memory_signal = (wins - losses) / k
    """
    trades = journal_data.get("trades", [])
    if len(trades) < k: return 0.0
    
    distances = []
    # Current features values
    cfeats = {k: v for k, v in current_features.items() if isinstance(v, (int, float))}
    
    for t in trades:
        tfeats = t.get("features", {})
        if not tfeats: continue
        
        # Calculate Euclidean distance on intersecting keys
        sq_dist = 0.0
        keys_computed = 0
        for fk, fv in cfeats.items():
            if fk in tfeats and isinstance(tfeats[fk], (int, float)):
                sq_dist += (fv - tfeats[fk])**2
                keys_computed += 1
                
        if keys_computed > 0:
            dist = math.sqrt(sq_dist)
            outcome = 1 if str(t.get("outcome")).upper() in ["WIN", "1"] else -1
            distances.append((dist, outcome))
            
    if not distances: return 0.0
    
    # Sort by closest distance
    distances.sort(key=lambda x: x[0])
    top_k = distances[:k]
    
    memory_score = sum(d[1] for d in top_k) / float(len(top_k))
    return memory_score

# =============================================================================
# SKILL EXTRACTION & LIFECYCLE
# =============================================================================
def extract_skill(trade_record):
    """Called after a winning trade with score > 30."""
    score = trade_record.get("monolithic_score", 0.0)
    outcome = str(trade_record.get("outcome", "")).upper()
    if outcome not in ["WIN", "1"] or score <= 30:
        return
        
    features = trade_record.get("features", {})
    if not features: return
    
    # Extract top 3 features by absolute magnitude as the "trigger conditions"
    sorted_feats = sorted([(k, v) for k, v in features.items() if isinstance(v, (int, float))], 
                          key=lambda x: abs(x[1]), reverse=True)
    
    if len(sorted_feats) < 3: return
    
    trigger_conditions = {}
    for k, v in sorted_feats[:3]:
        # Formulate a trigger band
        trigger_conditions[k] = {"center": v, "band": abs(v * 0.15)} # +/- 15% tolerance
        
    skills_data = load_json(SKILLS_FILE, {"skills": {}, "metadata": {}})
    skill_id = f"skill_{uuid.uuid4().hex[:8]}"
    
    skills_data["skills"][skill_id] = {
        "conditions": trigger_conditions,
        "confidence": 0.5, # Initial confidence
        "observations": 0,
        "wins": 0,
        "state": "NEW", # NEW -> DEVELOPING -> CORE
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    skills_data["metadata"]["total_skills_extracted"] = skills_data["metadata"].get("total_skills_extracted", 0) + 1
    save_json(SKILLS_FILE, skills_data)
    print(f"[SKILL SYSTEM] Minted new skill {skill_id} from highly profitable trade.")

def update_skills(trade_record):
    """Called after ANY trade closes. If a skill fired, update its confidence."""
    fired_skill_id = trade_record.get("fired_skill_id")
    if not fired_skill_id: return
    
    skills_data = load_json(SKILLS_FILE, {"skills": {}})
    skill = skills_data.get("skills", {}).get(fired_skill_id)
    if not skill: return
    
    outcome = str(trade_record.get("outcome", "")).upper()
    is_win = 1 if outcome in ["WIN", "1"] else 0
    
    skill["observations"] = skill.get("observations", 0) + 1
    skill["wins"] = skill.get("wins", 0) + is_win
    
    obs = skill["observations"]
    # Update confidence
    skill["confidence"] = skill["wins"] / float(obs)
    
    # State transition
    if obs >= 20 and skill["confidence"] >= 0.65:
        skill["state"] = "CORE"
    elif obs >= 10:
        if skill["confidence"] < 0.40:
            skill["state"] = "PRUNED"
        else:
            skill["state"] = "DEVELOPING"
            
    # Tighten conditions on wins
    if is_win:
        feats = trade_record.get("features", {})
        for cond_key, cond_val in skill.get("conditions", {}).items():
            if cond_key in feats and isinstance(feats[cond_key], (int, float)):
                # Shift center 10% toward the recent winning value
                old_center = cond_val["center"]
                new_val = feats[cond_key]
                cond_val["center"] = old_center * 0.9 + new_val * 0.1
                # Shrink band slightly (tighten)
                cond_val["band"] = cond_val["band"] * 0.98

    skills_data["skills"][fired_skill_id] = skill
    save_json(SKILLS_FILE, skills_data)
    action = "Pruned" if skill["state"] == "PRUNED" else "Updated"
    print(f"[SKILL SYSTEM] {action} {fired_skill_id} | Conf: {skill['confidence']:.2f} ({skill['state']})")

# =============================================================================
# SKILL MATCHING
# =============================================================================
def match_skills(current_features, skills_data):
    """
    Search stored skills for condition matches.
    Returns: (skill_id, skill_signal)
    """
    skills = skills_data.get("skills", {})
    best_skill = None
    best_conf = 0.0
    
    for s_id, skill in skills.items():
        if skill.get("state") == "PRUNED": continue
        
        conditions = skill.get("conditions", {})
        matches = 0
        for k, v in conditions.items():
            if k in current_features:
                val = current_features[k]
                center = v["center"]
                band = v["band"]
                if center - band <= val <= center + band:
                    matches += 1
                    
        # Require 3+ condition matches (or all if < 3 conditions exist)
        req_matches = min(3, len(conditions))
        if matches >= req_matches and req_matches > 0:
            conf = skill.get("confidence", 0.5)
            if conf > best_conf:
                best_conf = conf
                best_skill = s_id
                
    if best_skill:
        return best_skill, best_conf * 1.2
    return None, 0.0
