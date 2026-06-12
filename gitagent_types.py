from dataclasses import dataclass, field
from typing import Optional, Dict, List
import datetime

@dataclass
class EntryCognitiveStatePayload:
    """Payload for capturing initial cognitive state at trade entry."""
    raw_probability_vector: List[float]
    adjusted_conviction: float
    activity_ratio: float
    bocpd_prob: float
    wasserstein_idx: int
    volatility_ratio: float = 0.0
    ofi_velocity: float = 0.0

@dataclass
class RuntimeTelemetryPayload:
    """Payload for capturing continuous runtime telemetry during a trade."""
    bar_step: int
    current_pnl: float
    condition_number: float
    shaps: Dict[str, float]
    price: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    hmm_state: str = "UNKNOWN"
    conviction: float = 0.0

@dataclass
class ProposedTradePayload:
    """
    Unified telemetry payload for trade generation.
    Represents the intent before verification and execution.
    """
    symbol: str
    side: str  # "BUY" or "SELL"
    volume: float
    current_price: float
    requested_sl: float
    requested_tp: float
    
    # Oracle / Volatility Metadata
    macro_atr: float
    oracle_source: str = "TimesFM"
    variance_p10: Optional[float] = None
    variance_p90: Optional[float] = None
    
    # State tracking
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    is_verified: bool = False
    graceful_degradation_triggered: bool = False
    anomalies: list = field(default_factory=list)

    def log_anomaly(self, msg: str):
        self.anomalies.append(msg)

@dataclass
class ExecutionPermit:
    """
    Cryptographically sealed (conceptually) permit for live execution.
    Only instantiated with is_valid=True by VerificationEngine.
    """
    is_valid: bool
    request_dict: dict = field(default_factory=dict)
    rejection_reason: str = ""

class TelemetryState:
    """Unified telemetry registry for cross-layer auditing."""
    _audit_logs = []

    @classmethod
    def log_audit(cls, component: str, symbol: str, message: str):
        entry = f"[{datetime.datetime.utcnow().isoformat()}] [{component}] {symbol}: {message}"
        cls._audit_logs.append(entry)
        # Also print for debug visibility
        print(entry)

    @classmethod
    def get_logs(cls):
        return cls._audit_logs

