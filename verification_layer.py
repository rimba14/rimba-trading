import logging
from gitagent_types import ProposedTradePayload, ExecutionPermit
from profit_manager_v28_34 import calculate_institutional_hard_stop

logger = logging.getLogger("UnderwritingEngine")

class VerificationEngine:
    """
    Pillar 1 & 2: The Independent Underwriting Engine & Graceful Degradation Protocol.
    Sits strictly between Action Layer payload generation and Live Terminal execution.
    """

    def __init__(self, max_rr_ratio: float = 23.0):
        self.max_rr_ratio = max_rr_ratio

    def underwrite_payload(self, payload: ProposedTradePayload, draft_request: dict) -> ExecutionPermit:
        """
        Evaluates the trade payload against macro-risk invariants.
        Returns a cryptographically sealed ExecutionPermit if approved (modified in-place via Graceful Degradation).
        Returns an invalid ExecutionPermit if Hard Veto is triggered.
        """
        is_buy = (payload.side == "BUY")
        
        # Invariant 1: Institutional Hard Anchor Minimum Distance
        # We calculate what the absolute minimum hard anchor should be based on macro ATR
        # (Assuming 'NEUTRAL' HMM state for pre-flight safety if not provided)
        hard_anchor_price = calculate_institutional_hard_stop(
            payload.current_price, is_buy, payload.macro_atr, "NEUTRAL"
        )
        
        min_sl_dist = abs(payload.current_price - hard_anchor_price)
        requested_sl_dist = abs(payload.current_price - payload.requested_sl)
        
        if requested_sl_dist < min_sl_dist:
            # Pillar 2: Graceful Degradation Protocol
            payload.log_anomaly(
                f"Variance Sanity Gate Failed: Requested SL distance ({requested_sl_dist:.5f}) "
                f"is tighter than Institutional Floor ({min_sl_dist:.5f}). Triggering Graceful Degradation."
            )
            
            # Scale down volume by 50% for safety due to oracle variance anomaly
            old_vol = payload.volume
            payload.volume = round(payload.volume * 0.5, 2)
            # Ensure volume doesn't drop below absolute broker minimums (assuming 0.01 for now, but handled by Action Layer)
            if payload.volume < 0.01:
                payload.volume = 0.01
                
            payload.log_anomaly(f"Graceful Degradation: Scaled volume {old_vol} -> {payload.volume}")
            
            # Force overwrite the requested SL to the Macro ATR baseline
            payload.requested_sl = hard_anchor_price
            payload.graceful_degradation_triggered = True
            payload.log_anomaly(f"Graceful Degradation: Overwrote SL to {payload.requested_sl:.5f}")

        # Recalculate SL distance after potential Graceful Degradation
        final_sl_dist = abs(payload.current_price - payload.requested_sl)
        
        # Invariant 2: Distorted R:R Ratio Check (e.g., > 20:1)
        tp_dist = abs(payload.requested_tp - payload.current_price)
        if final_sl_dist > 0:
            rr_ratio = tp_dist / final_sl_dist
            if rr_ratio > self.max_rr_ratio:
                payload.log_anomaly(
                    f"Hard Veto: Risk:Reward ratio distorted ({rr_ratio:.2f}:1). "
                    f"Exceeds max allowed {self.max_rr_ratio}:1. Trade Rejected."
                )
                return ExecutionPermit(is_valid=False, rejection_reason="Hard Veto: Distorted R:R Ratio")

        payload.is_verified = True
        
        # Apply underwriting modifications to the draft request
        draft_request["sl"] = payload.requested_sl
        draft_request["tp"] = payload.requested_tp
        draft_request["volume"] = payload.volume
        
        return ExecutionPermit(is_valid=True, request_dict=draft_request)

# Global Verification Engine instance
underwriter = VerificationEngine()
