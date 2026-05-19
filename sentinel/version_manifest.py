"""
Sentinel Version Manifest (v28.30 - Ironclad CADES (Delayed Fortress Exit))
Canonical source of truth for system identity and trade signature tracking.

Wall 8 (Breathing Room): "Naive, continuous trailing stops are forbidden. Trades must be granted 'Breathing Room' to survive standard market noise. The Profit Manager may only engage a trailing stop after the position has crossed a minimum +1.5 R-Multiple threshold, or reached 80% of its absolute Take Profit target."

Wall 2 (State Isolation): "Minor assets are strictly forbidden from altering Global State variables. Tick starvation on a minor asset must be locally quarantined (is_this_symbol_starved). The global _TICK_STARVATION_DETECTED flag may ONLY be triggered if a defined CORE MAJOR asset loses its feed, signifying a broker-wide outage."

Wall 3 (Regime Failsafes): "Hardcoded boolean confidence cliffs (e.g., requiring > 60% probability) are deprecated in favor of Bayesian Mixture Priors (MixTS). The system shall trust the probabilistically blended P_blend score to clear the dynamic gate. Explicit directional conflicts (e.g., Selling in a Bull regime) remain strictly vetoed."

Wall 9 (Strategy-Regime Congruence): "It is constitutionally forbidden to deploy a Momentum strategy during a RANGE regime, or a Mean-Reversion strategy during a TREND regime. The HMM state is the supreme arbiter of strategy selection."
"""

SENTINEL_VERSION = "v28.30"
SENTINEL_BUILD = "IRONCLAD"
SENTINEL_CONSTITUTION = "CADES"
AGENT_SIGNATURE = f"SENTINEL_{SENTINEL_VERSION}_{SENTINEL_BUILD}_{SENTINEL_CONSTITUTION}"

# Banned signatures of legacy systems to prevent ghost executions
LEGACY_BANNED = ["v20.4", "v20.5", "v21.0", "v22.4", "v22.8", "v23.11", "v24.1", "v25.0", "v26.4", "v27.0", "v28.9", "v28.10", "v28.11", "v28.12", "v28.13", "v28.27", "v28.28", "v28.29"]
