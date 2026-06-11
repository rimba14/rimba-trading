"""
agent_quarantine.py
═══════════════════════════════════════════════════════════════════════════════
CADES Agent Quarantine — Prevents uninitialised agents from voting.

Problem solved
──────────────
v27.0: The DDQN agent had uninitialized weights. It scored 0.500 — the default
output of a random network. The multi-agent combiner treated this as a valid
signal, diluting the HMM+FinEmotion consensus from 0.745 → 0.7227. This false
precision implied two agents agreed, when only one had real predictive power.

Design
──────
Each agent must declare: is_initialized, training_episodes, last_updated.
The QuarantineRegistry tracks these states and exposes:
  • filter_agents()  — remove unqualified agents from a score dict
  • audit()          — return the status of every registered agent
  • require()        — decorator for agent score functions that raises if quarantined

Integration with alpha_combiner.py
───────────────────────────────────
In alpha_combiner.py :: AlphaCombiner.process_signals(), before z-scoring:

    from agent_quarantine import registry

    signals_dict = {
        sym: registry.filter_agents(scores)
        for sym, scores in signals_dict.items()
    }

    if not signals_dict or not any(signals_dict.values()):
        logger.warning("No qualified agents — skipping cycle")
        return {}

Register agents at startup (once):

    from agent_quarantine import registry, AgentState

    registry.register("hmm",          AgentState(is_initialized=True,  training_episodes=10000))
    registry.register("ddqn",         AgentState(is_initialized=False, training_episodes=0))
    registry.register("finemotion",   AgentState(is_initialized=True,  training_episodes=5000))
    registry.register("deep_research",AgentState(is_initialized=True,  training_episodes=None))

═══════════════════════════════════════════════════════════════════════════════
"""

import json
import logging
import functools
from dataclasses  import dataclass, field
from datetime     import datetime, timezone
from pathlib      import Path
from typing       import Any, Callable, Dict, List, Optional

logger = logging.getLogger("AgentQuarantine")


# ── Tunable thresholds ────────────────────────────────────────────────────────

MIN_TRAINING_EPISODES = 500     # Agents below this stay quarantined
MIN_AGENT_VERSION     = "1.0"   # Optional: gate on version string


# ── Agent state ───────────────────────────────────────────────────────────────

@dataclass
class AgentState:
    """
    Declare an agent's readiness for live participation.

    Fields
    ──────
    is_initialized       True if weights have been set (not random init).
    training_episodes    Number of completed training episodes. None = non-RL agent.
    version              Optional version string for tracking.
    last_updated         UTC timestamp of the last weight checkpoint.
    notes                Free-text diagnostic note.
    """
    is_initialized:    bool
    training_episodes: Optional[int] = None
    version:           Optional[str] = None
    last_updated:      Optional[str] = None   # ISO 8601 UTC
    notes:             str           = ""

    @property
    def is_qualified(self) -> bool:
        """
        True if the agent is allowed to participate in multi-agent voting.
        Rules:
          1. Must be initialized (weights set, not random).
          2. If it has a training counter, it must exceed MIN_TRAINING_EPISODES.
        """
        if not self.is_initialized:
            return False
        if (
            self.training_episodes is not None
            and self.training_episodes < MIN_TRAINING_EPISODES
        ):
            return False
        return True

    @property
    def disqualification_reason(self) -> Optional[str]:
        if not self.is_initialized:
            return f"uninitialised weights"
        if (
            self.training_episodes is not None
            and self.training_episodes < MIN_TRAINING_EPISODES
        ):
            return (
                f"insufficient training: "
                f"{self.training_episodes} < {MIN_TRAINING_EPISODES} episodes"
            )
        return None


@dataclass
class FilterResult:
    """Result returned by QuarantineRegistry.filter_agents()."""
    filtered_scores: Dict[str, float]   # Scores from qualified agents only
    quarantined:     Dict[str, str]     # {agent_name: disqualification_reason}
    total_agents:    int
    active_agents:   int

    @property
    def consensus_degraded(self) -> bool:
        """True if any agents were removed from the vote."""
        return len(self.quarantined) > 0

    def log_summary(self) -> None:
        if self.quarantined:
            logger.warning(
                "[Quarantine] %d/%d agents quarantined this cycle: %s",
                len(self.quarantined),
                self.total_agents,
                {k: v for k, v in self.quarantined.items()},
            )
        else:
            logger.debug(
                "[Quarantine] All %d agents qualified.", self.total_agents
            )


# ── Registry ──────────────────────────────────────────────────────────────────

class QuarantineRegistry:
    """
    Central registry of agent states. Thread-safe for reads; writes should
    happen at startup or between cycles, not during execution.
    """

    def __init__(self, persist_path: Optional[str] = "agent_states.json"):
        self._agents: Dict[str, AgentState] = {}
        self._persist_path = Path(persist_path) if persist_path else None
        if self._persist_path and self._persist_path.exists():
            self._load()

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, name: str, state: AgentState) -> None:
        """Register or update an agent's state."""
        self._agents[name] = state
        status = "QUALIFIED" if state.is_qualified else f"QUARANTINED ({state.disqualification_reason})"
        logger.info("[Quarantine] Agent '%s' registered → %s", name, status)
        self._save()

    def update(
        self,
        name:              str,
        is_initialized:    Optional[bool] = None,
        training_episodes: Optional[int]  = None,
        version:           Optional[str]  = None,
        notes:             Optional[str]  = None,
    ) -> None:
        """
        Partial update for an already-registered agent.
        Call this after a training checkpoint to promote an agent out of quarantine.
        """
        if name not in self._agents:
            raise KeyError(f"Agent '{name}' not registered. Call register() first.")

        state = self._agents[name]
        if is_initialized    is not None: state.is_initialized    = is_initialized
        if training_episodes is not None: state.training_episodes = training_episodes
        if version           is not None: state.version           = version
        if notes             is not None: state.notes             = notes
        state.last_updated = datetime.now(timezone.utc).isoformat()

        was_quarantined = not state.is_qualified
        new_status = "QUALIFIED" if state.is_qualified else f"QUARANTINED ({state.disqualification_reason})"
        if was_quarantined and state.is_qualified:
            logger.info("[Quarantine] Agent '%s' PROMOTED to QUALIFIED ✓", name)
        logger.info("[Quarantine] Agent '%s' updated → %s", name, new_status)
        self._save()

    # ── Core filter ───────────────────────────────────────────────────────────

    def filter_agents(
        self,
        scores: Dict[str, float],
        strict: bool = False,
    ) -> FilterResult:
        """
        Remove quarantined agents from a score dict.

        Parameters
        ──────────
        scores   Dict of {agent_name: score} from the multi-agent combiner.
        strict   If True and ALL agents are quarantined, return empty dict.
                 If False (default), pass through unregistered agents (they
                 are assumed to be operational — only registered-and-failed
                 agents are stripped).

        Returns
        ───────
        FilterResult with filtered_scores (ready to pass to AlphaCombiner)
        and a quarantined dict for logging/forensics.
        """
        filtered    = {}
        quarantined = {}

        # --- EDGE DECAY SENTINEL QUARANTINE HOOK (v31.2) ---
        state_file = "oracle_cache/edge_decay_state.json"
        decay_quarantine_agents = []
        try:
            import os, json
            if os.path.exists(state_file):
                with open(state_file, "r", encoding="utf-8") as fh:
                    state_data = json.load(fh)
                agent_tier = state_data.get("agent_tier", {})
                for a_name, a_status in agent_tier.items():
                    if a_status == "QUARANTINED":
                        decay_quarantine_agents.append(a_name.lower())
        except Exception as e:
            logger.warning(f"[DECAY_SRE_WARN] Telemetry agent quarantine check failed to load/parse: {e}")
        # ---------------------------------------------------

        for agent_name, score in scores.items():
            # Check dynamic SRE quarantine first
            matched_decay = False
            for dq_agent in decay_quarantine_agents:
                if dq_agent in agent_name.lower() or agent_name.lower() in dq_agent:
                    matched_decay = True
                    break
            
            if matched_decay:
                reason = "Edge Decay Quarantine (persistent hit-rate decay below 5th percentile)"
                quarantined[agent_name] = reason
                logger.warning(
                    "[Quarantine] Agent '%s' dynamically quarantined by SRE Sentinel (score %.4f dropped)",
                    agent_name, score,
                )
                continue

            state = self._agents.get(agent_name)

            if state is None:
                if strict:
                    reason = "not registered (strict mode)"
                    quarantined[agent_name] = reason
                    logger.warning(
                        "[Quarantine] Unregistered agent '%s' stripped (strict mode)", agent_name
                    )
                else:
                    # Unregistered = not known to be broken → pass through
                    filtered[agent_name] = score
                continue

            if state.is_qualified:
                filtered[agent_name] = score
            else:
                reason = state.disqualification_reason or "unknown"
                quarantined[agent_name] = reason
                logger.warning(
                    "[Quarantine] Agent '%s' quarantined: %s (score %.4f dropped)",
                    agent_name, reason, score,
                )

        result = FilterResult(
            filtered_scores = filtered,
            quarantined     = quarantined,
            total_agents    = len(scores),
            active_agents   = len(filtered),
        )
        result.log_summary()
        return result

    # ── Audit ─────────────────────────────────────────────────────────────────

    def audit(self) -> Dict[str, dict]:
        """Return the full status of every registered agent."""
        out = {}
        for name, state in self._agents.items():
            out[name] = {
                "qualified":           state.is_qualified,
                "is_initialized":      state.is_initialized,
                "training_episodes":   state.training_episodes,
                "version":             state.version,
                "last_updated":        state.last_updated,
                "disqualification":    state.disqualification_reason,
                "notes":               state.notes,
            }
        return out

    def print_audit(self) -> None:
        """Pretty-print the agent audit table to stdout."""
        print(f"\n{'Agent':<20}{'Qualified':>10}{'Episodes':>12}{'Reason'}")
        print("─" * 70)
        for name, info in self.audit().items():
            q   = "✓ YES" if info["qualified"] else "✗ NO"
            ep  = str(info["training_episodes"]) if info["training_episodes"] is not None else "N/A"
            rsn = info["disqualification"] or "—"
            print(f"{name:<20}{q:>10}{ep:>12}  {rsn}")

    # ── Decorator ─────────────────────────────────────────────────────────────

    def require(self, agent_name: str) -> Callable:
        """
        Decorator: the decorated agent score function only runs if the agent
        is qualified. Otherwise returns 0.0 and logs a quarantine notice.

        Usage:
            @registry.require("ddqn")
            def ddqn_score(features) -> float:
                return model.predict(features)
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> float:
                state = self._agents.get(agent_name)
                if state is None or state.is_qualified:
                    return func(*args, **kwargs)
                logger.warning(
                    "[Quarantine] @require('%s') blocked — %s. Returning 0.0.",
                    agent_name, state.disqualification_reason,
                )
                return 0.0   # sentinel: caller must check FilterResult
            return wrapper
        return decorator

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        if self._persist_path is None:
            return
        try:
            data = {
                name: {
                    "is_initialized":    s.is_initialized,
                    "training_episodes": s.training_episodes,
                    "version":           s.version,
                    "last_updated":      s.last_updated,
                    "notes":             s.notes,
                }
                for name, s in self._agents.items()
            }
            self._persist_path.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def _load(self) -> None:
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for name, d in data.items():
                self._agents[name] = AgentState(**d)
            logger.info(
                "[Quarantine] Loaded %d agent states from %s",
                len(self._agents), self._persist_path,
            )
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning("[Quarantine] Could not load agent states: %s", exc)


# ── Module-level singleton (import and use directly) ──────────────────────────

registry = QuarantineRegistry(persist_path="agent_states.json")


# ── Convenience: register the v27.0 known agents ─────────────────────────────

def register_default_agents() -> None:
    """
    Register the Sentinel's known agents with their v27.0 states.
    Call this ONCE at startup, before the slow loop begins.
    Update 'training_episodes' and 'is_initialized' as agents train.
    """
    registry.register("hmm",           AgentState(is_initialized=True,  training_episodes=None,  notes="HMM regime model"))
    registry.register("finemotion",    AgentState(is_initialized=True,  training_episodes=None,  notes="FinEmotion NLP sentiment"))
    registry.register("deep_research", AgentState(is_initialized=True,  training_episodes=None,  notes="Macro research daemon"))
    registry.register("ddqn",          AgentState(is_initialized=False, training_episodes=0,     notes="v27.0: uninitialized — quarantined"))
    registry.register("rl_agent",      AgentState(is_initialized=False, training_episodes=0,     notes="RL sub-agent — not yet trained"))
