"""
Sentinel Version Manifest (v29.0 - Multi-Modal Swing Trading)
Canonical source of truth for system identity and trade signature tracking.

Wall 8 (Execution Layer — Swing Trading Protocol): "Premature trailing stops are strictly prohibited, as they choke swing trades. The system calculates Target Path Distance (D_target = |Virtual_TP - Entry|). It establishes a guard at exactly 80% of the target (D_guard = 0.80 * D_target). The physical/virtual stop-loss is completely frozen at its initial location and absolutely prohibited from moving, trailing, or adjusting until the current price successfully breaches the 80% D_guard threshold. Take Profit distance must be structurally locked to a minimum of 1.5x the Stop Loss distance (Symmetric TP)."

Wall 2 (State Isolation): "Minor assets are strictly forbidden from altering Global State variables. Tick starvation on a minor asset must be locally quarantined (is_this_symbol_starved). The global _TICK_STARVATION_DETECTED flag may ONLY be triggered if a defined CORE MAJOR asset loses its feed, signifying a broker-wide outage."

Wall 3 (Regime Failsafes): "Hardcoded boolean confidence cliffs (e.g., requiring > 60% probability) are deprecated in favor of Bayesian Mixture Priors (MixTS). The system shall trust the probabilistically blended P_blend score to clear the dynamic gate. Explicit directional conflicts (e.g., Selling in a Bull regime) remain strictly vetoed."

Wall 9 (Strategy-Regime Congruence): "It is constitutionally forbidden to deploy a Momentum strategy during a RANGE regime, or a Mean-Reversion strategy during a TREND regime. The HMM state is the supreme arbiter of strategy selection."
"""

SENTINEL_VERSION = "v29.0"
SENTINEL_BUILD = "IRONCLAD"
SENTINEL_CONSTITUTION = "CADES"
AGENT_SIGNATURE = f"SENTINEL_{SENTINEL_VERSION}_{SENTINEL_BUILD}_{SENTINEL_CONSTITUTION}"

# Banned signatures of legacy systems to prevent ghost executions
LEGACY_BANNED = ["v20.4", "v20.5", "v21.0", "v22.4", "v22.8", "v23.11", "v24.1", "v25.0", "v26.4", "v27.0", "v28.9", "v28.10", "v28.11", "v28.12", "v28.13", "v28.27", "v28.28", "v28.29", "v28.30", "v28.31", "v28.35", "v28.36", "v28.37", "v28.38"]

