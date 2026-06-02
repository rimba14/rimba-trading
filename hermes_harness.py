import os
import glob
import subprocess
import logging
from enum import Enum
from typing import Optional, List, Tuple
from datetime import datetime, timezone

# -------------------------------------------------------------------------
# 1. DYNAMIC RUNTIME PROFILING (Harness Scaling)
# -------------------------------------------------------------------------

class EngineProfile(Enum):
    MINIMAL = 1
    STANDARD = 2
    STRICT = 3

class HarnessProfiler:
    def __init__(self, default_profile: EngineProfile = EngineProfile.MINIMAL):
        self.active_profile = default_profile
        self.logger = logging.getLogger("HermesHarness")
        
    def set_profile(self, profile: EngineProfile):
        self.active_profile = profile
        self.logger.info(f"Harness Profile shifted to: {self.active_profile.name}")
        
    def evaluate_regime_shift(self, is_high_volatility: bool, is_sre_active: bool):
        """Automatically scales the runtime harness based on active environmental threats."""
        if is_high_volatility or is_sre_active:
            self.set_profile(EngineProfile.STRICT)
        else:
            self.set_profile(EngineProfile.MINIMAL)

    def log_trace(self, message: str):
        """Throttles deep diagnostic traces based on profile state to preserve tokens."""
        if self.active_profile == EngineProfile.STRICT:
            self.logger.debug(f"[STRICT TRACE] {message}")
        elif self.active_profile == EngineProfile.STANDARD:
            self.logger.info(f"[STANDARD TRACE] {message}")
        else:
            # MINIMAL suppresses trace overhead entirely.
            pass

# -------------------------------------------------------------------------
# 2. MULTI-LAYER RE-ENTRANCY & OBSERVER LOOP GUARDS
# -------------------------------------------------------------------------

class SRECircuitBreaker:
    def __init__(self, root_dir: str = "C:/Sentinel_Project"):
        self.root_dir = root_dir
        self.consecutive_failures = 0
        self.MAX_FAILURES = 3

    def record_success(self):
        self.consecutive_failures = 0

    def record_failure(self) -> Tuple[bool, str]:
        """
        Increments failure count and trips hardware breaker if threshold exceeded.
        Returns: (is_tripped, message)
        """
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.MAX_FAILURES:
            msg = self._trip_circuit_breaker()
            return True, msg
        return False, f"Failure {self.consecutive_failures}/{self.MAX_FAILURES} recorded."

    def _trip_circuit_breaker(self) -> str:
        """Halts the observer loop, rolls back, and generates a critical core dump."""
        dump_file = os.path.join(self.root_dir, "SRE_FATAL_CORE_DUMP.txt")
        with open(dump_file, "w") as f:
            f.write(f"FATAL: SRE Circuit Breaker tripped at {datetime.now(timezone.utc).isoformat()} UTC\n")
            f.write(f"Cause: {self.MAX_FAILURES} consecutive script compilation/syntax failures detected.\n")
            f.write("Action: Loop halted. Awaiting manual rollback or secondary agent evaluation.\n")
        
        # In a full deployment, this triggers git checkout . or git checkout <stable_tag>.
        self._execute_rollback()
        
        return f"[FATAL] Circuit breaker tripped. Wrote core dump to {dump_file}. Observer loop MUST halt immediately."

    def _execute_rollback(self):
        try:
            # Attempt to roll back modified files utilizing the git index.
            subprocess.run(["git", "checkout", "."], cwd=self.root_dir, check=False)
        except Exception as e:
            pass # Failsafe wrapper

# -------------------------------------------------------------------------
# 3. CONTEXT MEMORY PRUNING & TAIL SAMPLING
# -------------------------------------------------------------------------

class LogPruner:
    @staticmethod
    def tail_sample_log(filepath: str, n_lines: int = 50) -> List[str]:
        """Reads only the last N relevant lines to prevent LLM token bloat."""
        if not os.path.exists(filepath):
            return []
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            return lines[-n_lines:] if len(lines) > n_lines else lines

    @staticmethod
    def aggressive_cleanup(directories: List[str]):
        """Purges all temporary diagnostic traces and evaluation garbage."""
        for directory in directories:
            if not os.path.exists(directory):
                continue
            for pattern in ["*.log", "*.tmp", "*_trace.txt"]:
                for filepath in glob.glob(os.path.join(directory, pattern)):
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass # Ignore locking errors

# -------------------------------------------------------------------------
# 4. PORTABLE STATUS SERIALIZATION (TRADING_STATUS.MD)
# -------------------------------------------------------------------------

class StatusEngine:
    def __init__(self, filepath: str = "C:/Sentinel_Project/TRADING_STATUS.md"):
        self.filepath = filepath

    def update_status(self, 
                      hmm_regime: str, 
                      variance: float, 
                      kalman_residual: float, 
                      active_tickets: int,
                      sre_status: str,
                      memory_mb: float,
                      active_profile: EngineProfile):
        """Programmatically overwrites the centralized readiness board."""
        
        status_md = f"""# Sentinel Trading Matrix Status
**Last Updated:** {datetime.now(timezone.utc).isoformat()} UTC
**Engine Profile:** `{active_profile.name}`

## 1. Market Regime State
- **HMM Oracle Status:** `{hmm_regime}`
- **Portfolio Variance Metric:** `{variance:.4f}`

## 2. Tracking Alignment
- **Kalman Filter Residual Error:** `{kalman_residual:.5f}`

## 3. SRE Loop Diagnostics
- **Agent Status:** `{sre_status}`
- **Active Open Tickets:** `{active_tickets}`

## 4. Harness Health
- **Memory Footprint:** `{memory_mb:.1f} MB`
- **Circuit Breaker Status:** `[CLEAN]`
"""
        with open(self.filepath, "w", encoding='utf-8') as f:
            f.write(status_md)

# Singleton Hooks for easy importing
profiler = HarnessProfiler()
circuit_breaker = SRECircuitBreaker()
log_pruner = LogPruner()
status_engine = StatusEngine()