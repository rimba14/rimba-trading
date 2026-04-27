"""
GitAgent v5.9 — Self-Improving Weight Adjuster
Inspired by karpathy/autoresearch: agents improve by learning from their own trade outcomes.

HOW IT WORKS:
1. When a trade is executed, we log the agent vote scores that led to the decision.
2. After each scan cycle, we check MT5 deal history for closed positions.
3. If the trade was PROFITABLE → boost the voting agents' weights.
4. If the trade was a LOSS → penalize the voting agents' weights.
5. Weights are saved to gitagent_weights.json and persist between sessions.

This is the trading equivalent of Karpathy's val_bpb metric optimization loop.
"""

import json
import os
import MetaTrader5 as mt5
from datetime import datetime, timedelta

# ─── PATHS ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_FILE = os.path.join(BASE_DIR, "gitagent_weights.json")
TRADE_LOG_FILE = os.path.join(BASE_DIR, "gitagent_trade_log.json")
MDA_FILE = os.path.join(BASE_DIR, "gitagent_mda.json")

# ─── DEFAULT AGENT WEIGHTS (v5.8 baseline) ───
DEFAULT_WEIGHTS = {
    "W":   1.2,   # Williams
    "Wy":  1.0,   # Wyckoff
    "B":   0.9,   # Brooks
    "SMC": 1.15,  # SMC / ICT
    "MB":  1.25,  # Burry
    "RPB": 1.4,   # RPBERT
    "LLM": 1.5,   # Multi-LLM Consensus
    "WHL": 1.3,   # Whale Tracking
    "SEN": 1.0,   # Sentiment
}

# ─── LEARNING HYPERPARAMETERS ───
LEARN_RATE   = 0.05   # How much to adjust weights per trade outcome
MIN_WEIGHT   = 0.3    # Floor — agents never fully dropped
MAX_WEIGHT   = 2.5    # Ceiling — prevent domination
DECAY_RATE   = 0.002  # Slight decay each cycle to prevent runaway drift

def load_weights() -> dict:
    """Load persisted weights or return defaults."""
    if os.path.exists(WEIGHTS_FILE):
        with open(WEIGHTS_FILE, "r") as f:
            weights = json.load(f)
        # Ensure any new agents added get their default weight
        for k, v in DEFAULT_WEIGHTS.items():
            if k not in weights:
                weights[k] = v
        return weights
    return DEFAULT_WEIGHTS.copy()

def save_weights(weights: dict):
    """Persist weights to disk."""
    with open(WEIGHTS_FILE, "w") as f:
        json.dump(weights, f, indent=2)
    print(f"[LEARN] Weights saved to {WEIGHTS_FILE}")

def load_trade_log() -> list:
    """Load the trade outcome log."""
    if os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, "r") as f:
            return json.load(f)
    return []

def save_trade_log(log: list):
    with open(TRADE_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)

def log_trade(ticket: int, sym: str, sig: str, agent_buy_scores: dict, agent_sell_scores: dict):
    """
    Called immediately after a trade is executed.
    Records which agent voted what, so we can attribute the outcome later.
    """
    log = load_trade_log()
    entry = {
        "ticket": ticket,
        "sym": sym,
        "sig": sig,  # "BUY" or "SELL"
        "timestamp": datetime.now().isoformat(),
        "agent_buy_scores": agent_buy_scores,
        "agent_sell_scores": agent_sell_scores,
        "outcome": None,  # Will be filled in later
        "pnl": None,
    }
    log.append(entry)
    save_trade_log(log)
    print(f"[LEARN] Trade #{ticket} logged for {sym} ({sig})")

def check_and_learn():
    """
    Main learning loop — call this at the START of each scan cycle.
    1. Reads MT5 deal history for the last 7 days.
    2. Matches closed deals to our trade log.
    3. Adjusts weights based on profit/loss.
    """
    log = load_trade_log()
    weights = load_weights()

    if not log:
        print("[LEARN] No trades in log yet. Nothing to learn from.")
        return weights

    # Pull recent deals from MT5 (last 7 days)
    from_date = datetime.now() - timedelta(days=7)
    deals = mt5.history_deals_get(from_date, datetime.now())
    if deals is None:
        print("[LEARN] No deal history available.")
        return weights

    # Build a quick-lookup dict by ticket
    deal_map = {}
    for d in deals:
        # Only look at closed position deals (entry_type = 1 = out)
        if d.entry == mt5.DEAL_ENTRY_OUT:
            deal_map[d.position_id] = d

    updated = False
    for entry in log:
        if entry["outcome"] is not None:
            continue  # Already processed

        ticket = entry["ticket"]
        if ticket in deal_map:
            deal = deal_map[ticket]
            pnl = deal.profit
            entry["pnl"] = pnl
            entry["outcome"] = "WIN" if pnl > 0 else "LOSS"

            print(f"[LEARN] Trade #{ticket} ({entry['sym']}) closed: {entry['outcome']} | P&L: ${pnl:.2f}")

            # ─── WEIGHT ADJUSTMENT ───
            direction = entry["sig"]  # "BUY" or "SELL"
            buy_scores = entry["agent_buy_scores"]
            sell_scores = entry["agent_sell_scores"]

            for agent_key in weights:
                buy_v  = buy_scores.get(agent_key, 0.5)
                sell_v = sell_scores.get(agent_key, 0.5)

                # Which way did this agent vote?
                agent_voted_buy  = buy_v  > sell_v
                agent_voted_sell = sell_v > buy_v

                trade_was_buy  = direction == "BUY"
                trade_was_sell = direction == "SELL"

                agent_was_correct = (
                    (trade_was_buy  and agent_voted_buy  and pnl > 0) or
                    (trade_was_sell and agent_voted_sell and pnl > 0)
                )
                agent_was_wrong = (
                    (trade_was_buy  and agent_voted_buy  and pnl < 0) or
                    (trade_was_sell and agent_voted_sell and pnl < 0)
                )

                if agent_was_correct:
                    weights[agent_key] = min(weights[agent_key] + LEARN_RATE, MAX_WEIGHT)
                elif agent_was_wrong:
                    weights[agent_key] = max(weights[agent_key] - LEARN_RATE, MIN_WEIGHT)

            # ─── MDA Tracking ───
            # Update rolling accuracy per agent
            mda = load_mda()
            for agent_key in weights:
                buy_v  = buy_scores.get(agent_key, 0.5)
                sell_v = sell_scores.get(agent_key, 0.5)
                agent_voted_buy  = buy_v > sell_v
                agent_voted_sell = sell_v > buy_v
                was_win = pnl > 0
                correct = (direction == "BUY" and agent_voted_buy and was_win) or \
                          (direction == "SELL" and agent_voted_sell and was_win) or \
                          (direction == "BUY" and not agent_voted_buy and not was_win) or \
                          (direction == "SELL" and not agent_voted_sell and not was_win)
                if agent_key not in mda:
                    mda[agent_key] = {"correct": 0, "total": 0}
                mda[agent_key]["total"] += 1
                if correct:
                    mda[agent_key]["correct"] += 1
            save_mda(mda)

            updated = True

    # Apply gradual decay to all weights each cycle (prevents runaway drift)
    for k in weights:
        target = DEFAULT_WEIGHTS.get(k, 1.0)
        # Nudge slightly toward baseline
        weights[k] = weights[k] - DECAY_RATE * (weights[k] - target)
        weights[k] = round(max(MIN_WEIGHT, min(MAX_WEIGHT, weights[k])), 4)

    if updated:
        save_weights(weights)
        save_trade_log(log)
        print(f"[LEARN] Weights updated based on trade outcomes:")
        for k, v in weights.items():
            default = DEFAULT_WEIGHTS.get(k, 1.0)
            diff = v - default
            arrow = "+" if diff > 0.01 else "-" if diff < -0.01 else "="
            print(f"  {k:<5}: {v:.4f} {arrow} (baseline: {default:.2f})")
    else:
        print("[LEARN] No new closed trades to learn from this cycle.")

    return weights

def load_mda() -> dict:
    """Load the MDA (feature importance) tracking data."""
    if os.path.exists(MDA_FILE):
        with open(MDA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_mda(mda: dict):
    with open(MDA_FILE, "w") as f:
        json.dump(mda, f, indent=2)

def print_weight_report():
    """Print current weights vs baseline and MDA feature importance."""
    weights = load_weights()
    mda = load_mda()

    print("\n=== GITAGENT SELF-IMPROVEMENT REPORT ===")
    print(f"{'Agent':<8} {'Current':<10} {'Baseline':<10} {'Delta':<10} {'Trend'}")
    print("-" * 50)
    for k, v in weights.items():
        baseline = DEFAULT_WEIGHTS.get(k, 1.0)
        delta = v - baseline
        trend = "+ BOOSTED" if delta > 0.05 else "- PENALIZED" if delta < -0.05 else "= STABLE"
        print(f"{k:<8} {v:<10.4f} {baseline:<10.2f} {delta:+.4f}    {trend}")
    print("=" * 50)

    if mda:
        print("\n=== MDA FEATURE IMPORTANCE ===")
        # Compute accuracy per agent and rank
        ranked = []
        for k, v in mda.items():
            acc = v['correct'] / v['total'] if v['total'] > 0 else 0.0
            ranked.append((k, acc, v['correct'], v['total']))
        ranked.sort(key=lambda x: x[1], reverse=True)
        print(f"{'Agent':<8} {'Accuracy':<12} {'Correct':<10} {'Total':<8} {'Importance'}")
        print("-" * 55)
        for k, acc, correct, total in ranked:
            bar = "#" * int(acc * 10)
            print(f"{k:<8} {acc:<12.1%} {correct:<10} {total:<8} {bar}")
        print("=" * 55)


if __name__ == "__main__":
    # Standalone test: print current weight report
    mt5.initialize()
    check_and_learn()
    print_weight_report()
    mt5.shutdown()
