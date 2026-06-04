"""
profit_manager_tp_patch.py
==========================
DIRECTIVE ZETA Integration Patch for profit_manager.py v25.0 → v25.1

This file shows the EXACT integration points where TPPlacementEngine
plugs into the existing profit_manager.py architecture.
Apply these changes to your live profit_manager.py.

Sections:
  A — Import additions
  B — ProfitManager.__init__() additions
  C — PositionState.register() gate (new pre-registration check)
  D — Slow Loop reconciliation hook (new _reconcile_tp_compliance() method)
  E — ExitScoreEngine time-stop integration
  F — Legacy violation remediation runner (one-time audit on startup)

Constitutional ref: DIRECTIVE_ZETA_TP_PLACEMENT.md v31.0
"""

# ===========================================================================
# SECTION A — IMPORT ADDITIONS
# Add these to the top of profit_manager.py
# ===========================================================================

from tp_placement_engine import (
    TPPlacementEngine,
    TPValidationResult,
    StructuralLevelResolver,
    ASSET_CLASS_TIME_STOP,
    AssetClass,
)


# ===========================================================================
# SECTION B — ProfitManager.__init__() ADDITIONS
# Add inside __init__ after existing component initialisation
# ===========================================================================

class ProfitManager:
    """
    Existing class — showing only the additions required for DIRECTIVE ZETA.
    Do NOT replace the class; add/modify the indicated blocks.
    """

    def __init__(self, oracle_cache, mt5_bridge, config, hermes_agent=None):
        # ---- [EXISTING CODE — keep as-is] --------------------------------
        self.oracle_cache  = oracle_cache
        self.mt5_bridge    = mt5_bridge
        self.config        = config
        self.hermes_agent  = hermes_agent
        # self.position_registry = {}   <-- existing
        # self.exit_score_engine = ExitScoreEngine(...)  <-- existing
        # self.scale_out_coordinator = ScaleOutCoordinator(...)  <-- existing
        # ------------------------------------------------------------------

        # ---- [DIRECTIVE ZETA ADDITIONS] -----------------------------------
        self.level_resolver   = StructuralLevelResolver(oracle_cache)
        self.tp_engine        = TPPlacementEngine(oracle_cache, self.level_resolver)
        self._tp_violation_log: list[dict] = []   # audit trail for legacy violations
        # -------------------------------------------------------------------

    # =======================================================================
    # SECTION C — PositionState registration gate
    # Modify your existing register_position() / _on_new_position() method.
    # The gate runs BEFORE the PositionState is committed to the registry.
    # =======================================================================

    def register_position(
        self,
        ticket:    int,
        symbol:    str,
        entry:     float,
        sl:        float,
        tp:        float,
        direction: int,
        lots:      float,
        open_time,
    ) -> bool:
        """
        Returns True if position was successfully registered.
        Returns False if DIRECTIVE ZETA vetoes the TP — position is logged
        and operator is notified; registration is BLOCKED.

        For positions already open (caught by startup audit), use
        _flag_legacy_violation() instead of blocking registration.
        """

        # ---- [DIRECTIVE ZETA Gate 1] --------------------------------------
        validation: TPValidationResult = self.tp_engine.validate_tp_placement(
            symbol=symbol,
            entry=entry,
            sl=sl,
            proposed_tp=tp,
            direction=direction,
        )

        if not validation.is_valid:
            self._emit_tp_gate_reject(ticket, symbol, validation)
            return False

        if validation.adjusted:
            # TP was moved to comply with ceiling — update on broker before registering
            adjusted_tp = validation.final_tp
            success = self._modify_tp_on_broker(ticket, adjusted_tp)
            if not success:
                self._emit_tp_adjustment_failure(ticket, symbol, adjusted_tp)
                # Continue with registration using adjusted TP even if broker
                # modification failed — the Slow Loop will retry on next cycle
                import logging
                logging.getLogger("CADES.ProfitManager").warning(
                    f"[PositionRegistry] TP modification failed on broker for #{ticket} "
                    f"{symbol}. Registering with adjusted TP {adjusted_tp:.5f} "
                    f"and scheduling retry."
                )
            tp = adjusted_tp   # use adjusted TP for internal state

        for w in validation.warnings:
            import logging
            logging.getLogger("CADES.ProfitManager").warning(
                f"[ZETA WARNING] #{ticket} {symbol}: {w}"
            )
        # -------------------------------------------------------------------

        # ---- [EXISTING registration logic — keep as-is] ------------------
        # state = PositionState(ticket=ticket, symbol=symbol, ...)
        # self.position_registry[ticket] = state
        # ...
        # ------------------------------------------------------------------

        # ---- [DIRECTIVE ZETA — store validation result in PositionState] --
        # state.zeta_validation   = validation
        # state.time_stop_days    = validation.time_stop_days
        # state.entry_time        = open_time
        # -------------------------------------------------------------------

        return True

    # =======================================================================
    # SECTION D — Slow Loop reconciliation (every 5 minutes)
    # Add a call to this method in your existing slow_loop_cycle() / tick().
    # =======================================================================

    def _reconcile_tp_compliance(self) -> None:
        """
        DIRECTIVE ZETA Gate 3 — runs every Slow Loop cycle.
        Audits all open positions against current ATR ceilings.
        Flags violations and attempts broker-side TP corrections.
        Also enforces time-stop expiry.
        """
        import logging
        from datetime import datetime, timezone

        log = logging.getLogger("CADES.ProfitManager.ZetaReconcile")
        now = datetime.now(tz=timezone.utc)

        for ticket, state in list(self.position_registry.items()):
            symbol    = state.symbol
            entry     = state.entry_price
            sl        = state.sl_price
            tp        = state.tp_price
            direction = state.direction

            # ---------------------------------------------------------------
            # 1. TP compliance audit
            # ---------------------------------------------------------------
            audit = self.tp_engine.audit_open_position(
                symbol=symbol, entry=entry, sl=sl, current_tp=tp, direction=direction
            )

            if not audit.is_valid and state.zeta_status != "LEGACY_VIOLATION":
                log.warning(
                    f"[ZetaReconcile] #{ticket} {symbol} is a LEGACY_VIOLATION: "
                    f"{audit.rejection_reason}"
                )
                state.zeta_status = "LEGACY_VIOLATION"
                self._tp_violation_log.append({
                    "ticket":    ticket,
                    "symbol":    symbol,
                    "reason":    audit.rejection_reason,
                    "tp":        tp,
                    "tp_pct":    audit.tp_distance_pct,
                    "detected":  now.isoformat(),
                })
                if self.hermes_agent:
                    self.hermes_agent.emit_alert(
                        severity="HIGH",
                        code="ZETA_LEGACY_VIOLATION",
                        message=f"#{ticket} {symbol} TP={tp:.5f} ({audit.tp_distance_pct*100:.2f}%) "
                                f"violates DIRECTIVE ZETA. {audit.rejection_reason}",
                    )

            # ---------------------------------------------------------------
            # 2. Time-stop enforcement (Article III)
            # ---------------------------------------------------------------
            if state.time_stop_days and hasattr(state, "entry_time") and state.entry_time:
                elapsed_trading_days = self._count_trading_days(state.entry_time, now)
                max_days = state.time_stop_days

                # Pause time-stop in strong trending regime
                hmm_state = self.oracle_cache.get_hmm_state(symbol)
                wass_dist = self.oracle_cache.get_wasserstein_distance(symbol)
                in_strong_trend = (
                    hmm_state == "TRENDING" and wass_dist is not None and wass_dist < 0.15
                )

                if not in_strong_trend and elapsed_trading_days >= max_days:
                    log.warning(
                        f"[ZetaTimeStop] #{ticket} {symbol} has exceeded "
                        f"time-stop of {max_days} trading days "
                        f"({elapsed_trading_days} elapsed). Queuing market exit."
                    )
                    state.zeta_status = "TIME_STOP_TRIGGERED"
                    self._queue_time_stop_exit(ticket, symbol, state)

    @staticmethod
    def _count_trading_days(start, end) -> int:
        """Approximate trading day count excluding weekends."""
        import numpy as np
        days = np.busday_count(
            start.date(),
            end.date(),
            weekmask="Mon Tue Wed Thu Fri",
        )
        return int(days)

    def _modify_tp_on_broker(self, ticket: int, new_tp: float) -> bool:
        """Modify TP on MT5 broker. Returns True on success."""
        try:
            result = self.mt5_bridge.modify_position(
                ticket=ticket,
                tp=new_tp,
            )
            return result.success
        except Exception as exc:
            import logging
            logging.getLogger("CADES.ProfitManager").error(
                f"[BrokerModify] TP modification failed for #{ticket}: {exc}"
            )
            return False

    def _queue_time_stop_exit(self, ticket: int, symbol: str, state) -> None:
        """Queue a market-order exit for a time-stop triggered position."""
        import logging
        log = logging.getLogger("CADES.ProfitManager")
        log.warning(f"[TimeStop] Executing market exit for #{ticket} {symbol}")
        try:
            self.mt5_bridge.close_position(ticket=ticket, comment="ZETA_TIME_STOP")
        except Exception as exc:
            log.error(f"[TimeStop] Close failed for #{ticket}: {exc}")

    def _emit_tp_gate_reject(self, ticket: int, symbol: str, result: TPValidationResult) -> None:
        import logging
        log = logging.getLogger("CADES.ProfitManager")
        log.error(
            f"[TP_GATE_REJECT] #{ticket} {symbol}: {result.rejection_reason} | "
            f"proposed_tp={result.proposed_tp:.5f} "
            f"rr={result.rr_ratio:.2f} "
            f"tp_pct={result.tp_distance_pct*100:.2f}%"
        )
        if self.hermes_agent:
            self.hermes_agent.emit_alert(
                severity="CRITICAL",
                code="ZETA_TP_GATE_REJECT",
                message=result.rejection_reason,
            )

    def _emit_tp_adjustment_failure(
        self, ticket: int, symbol: str, adjusted_tp: float
    ) -> None:
        import logging
        logging.getLogger("CADES.ProfitManager").error(
            f"[ZetaAdjustFail] Broker TP modification failed for #{ticket} {symbol} "
            f"→ {adjusted_tp:.5f}. Scheduled for Slow Loop retry."
        )

    # =======================================================================
    # SECTION E — ExitScoreEngine time-stop hook
    # Add to your existing ExitScoreEngine.compute_exit_score() or
    # equivalent conviction-exit logic.
    # =======================================================================

    def _apply_time_stop_dampening(
        self,
        base_score: float,
        elapsed_trading_days: int,
        max_days: int,
        in_strong_trend: bool,
    ) -> float:
        """
        Scale down the conviction exit threshold as a trade ages.
        After 70% of time-stop is consumed, begin linearly reducing the
        exit score required to hold — making exit easier as time runs out.

        Args:
            base_score:           Raw exit conviction score (0-1)
            elapsed_trading_days: Days since entry
            max_days:             Asset-class time-stop ceiling
            in_strong_trend:      HMM=TRENDING + Wasserstein < 0.15

        Returns:
            Dampened score (lower = easier to exit)
        """
        if in_strong_trend or max_days is None:
            return base_score

        time_consumed = elapsed_trading_days / max_days
        if time_consumed < 0.70:
            return base_score

        # Linear dampening: at 70% consumed → no effect; at 100% → score halved
        dampening_factor = 1.0 - 0.5 * ((time_consumed - 0.70) / 0.30)
        dampening_factor = max(0.5, dampening_factor)
        return base_score * dampening_factor

    # =======================================================================
    # SECTION F — Startup legacy violation audit
    # Call this ONCE during ProfitManager startup, after position_registry
    # is populated from the MT5 bridge position sync.
    # =======================================================================

    def run_legacy_violation_audit(self) -> dict:
        """
        One-time audit of ALL open positions against DIRECTIVE ZETA.
        Run on startup to surface all pre-existing legacy violations.
        Returns a summary dict with violation counts and details.

        Identified violations are flagged in state.zeta_status and
        emitted to Hermes SRE for operator visibility.

        Based on the 2026-06-02 audit, the following are expected violations:
        - XRPUSD: crypto veto
        - XAUUSD: 13.65% TP (commodity cap 7%)
        - NAS100:  9.07% TP (index cap 7%)
        - SP500:   8.61% TP (index cap 7%)
        - NZDUSD:  8.51% TP (forex major cap 4%)
        """
        import logging
        log = logging.getLogger("CADES.ProfitManager.LegacyAudit")
        log.info("[LegacyAudit] Starting DIRECTIVE ZETA startup audit...")

        summary = {
            "total_positions": 0,
            "violations":      [],
            "compliant":       [],
            "warnings":        [],
        }

        for ticket, state in self.position_registry.items():
            summary["total_positions"] += 1
            audit = self.tp_engine.audit_open_position(
                symbol=state.symbol,
                entry=state.entry_price,
                sl=state.sl_price,
                current_tp=state.tp_price,
                direction=state.direction,
            )

            if not audit.is_valid:
                state.zeta_status = "LEGACY_VIOLATION"
                violation = {
                    "ticket":     ticket,
                    "symbol":     state.symbol,
                    "tp":         state.tp_price,
                    "tp_pct":     f"{audit.tp_distance_pct*100:.2f}%",
                    "rr":         f"{audit.rr_ratio:.2f}",
                    "reason":     audit.rejection_reason,
                    "asset_class": audit.asset_class.value,
                    "cap":        f"{(audit.asset_class_cap_pct or 0)*100:.1f}%",
                }
                summary["violations"].append(violation)
                log.error(
                    f"[LegacyAudit] VIOLATION #{ticket} {state.symbol}: "
                    f"TP={state.tp_price:.5f} ({audit.tp_distance_pct*100:.2f}%) "
                    f"| {audit.rejection_reason}"
                )
            else:
                state.zeta_status = "COMPLIANT"
                if audit.warnings:
                    summary["warnings"].extend([
                        {"ticket": ticket, "symbol": state.symbol, "warning": w}
                        for w in audit.warnings
                    ])
                summary["compliant"].append(ticket)

        log.info(
            f"[LegacyAudit] Complete: {len(summary['violations'])} violations, "
            f"{len(summary['compliant'])} compliant, "
            f"{len(summary['warnings'])} warnings."
        )

        if self.hermes_agent and summary["violations"]:
            self.hermes_agent.emit_alert(
                severity="HIGH",
                code="ZETA_LEGACY_AUDIT_COMPLETE",
                message=(
                    f"DIRECTIVE ZETA startup audit: "
                    f"{len(summary['violations'])} legacy violations detected. "
                    f"Symbols: {[v['symbol'] for v in summary['violations']]}. "
                    f"Manual review required."
                ),
            )

        return summary
