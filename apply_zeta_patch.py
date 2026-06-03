import os
import re

FILE_PATH = "C:\\Sentinel_Project\\profit_manager_v28_34.py"

with open(FILE_PATH, 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Imports (replace first occurrence only)
if 'from tp_placement_engine import' not in code:
    imports = """
from tp_placement_engine import (
    TPPlacementEngine,
    TPValidationResult,
    StructuralLevelResolver,
    ASSET_CLASS_TIME_STOP,
    AssetClass,
)
"""
    code = code.replace("import MetaTrader5 as mt5", "import MetaTrader5 as mt5" + imports, 1)

# 2. Init
if 'self.tp_engine' not in code:
    init_code = """
        self.level_resolver   = StructuralLevelResolver(self._oracle)
        self.tp_engine        = TPPlacementEngine(self._oracle, self.level_resolver)
        self._tp_violation_log = []
        self.hermes_agent = None
"""
    code = code.replace("self._oracle  = OracleCache(ttl=REGIME_POLL_INTERVAL)", "self._oracle  = OracleCache(ttl=REGIME_POLL_INTERVAL)" + init_code)

# 3. Add methods at the end of SentinelProfitManager
methods = """
    def _reconcile_tp_compliance(self) -> None:
        import logging
        from datetime import datetime, timezone
        log = logging.getLogger("CADES.ProfitManager.ZetaReconcile")
        now = datetime.now(tz=timezone.utc)

        for ticket, state in list(self._states.items()):
            symbol    = state.symbol
            entry     = state.entry_price
            sl        = state.initial_sl
            tp        = state.peak_price # placeholder, we don't store actual TP in PositionState, we can get it from MT5 position. 
            direction = 0 if state.direction == mt5.ORDER_TYPE_BUY else 1

            pos_info = mt5.position_get(ticket=ticket)
            if pos_info:
                current_tp = pos_info[0].tp
                sl = pos_info[0].sl
            else:
                continue

            audit = self.tp_engine.audit_open_position(
                symbol=symbol, entry=entry, sl=sl, current_tp=current_tp, direction=direction
            )

            if not audit.is_valid and getattr(state, "zeta_status", "") != "LEGACY_VIOLATION":
                log.warning(f"[ZetaReconcile] #{ticket} {symbol} is a LEGACY_VIOLATION: {audit.rejection_reason}")
                state.zeta_status = "LEGACY_VIOLATION"
                self._tp_violation_log.append({
                    "ticket":    ticket,
                    "symbol":    symbol,
                    "reason":    audit.rejection_reason,
                    "tp":        current_tp,
                    "tp_pct":    audit.tp_distance_pct,
                    "detected":  now.isoformat(),
                })

            # 2. Time-stop enforcement (Article III)
            max_days = getattr(state, "time_stop_days", None)
            if max_days and getattr(state, "entry_time", None):
                elapsed_trading_days = self._count_trading_days(datetime.fromtimestamp(state.entry_time, timezone.utc), now)

                hmm_state = self._oracle.get(symbol).get("hmm_state", "RANGE") if self._oracle.get(symbol) else "RANGE"
                wass_dist = 0.20 # Default

                in_strong_trend = (hmm_state == "TRENDING" and wass_dist is not None and wass_dist < 0.15)
                if not in_strong_trend and elapsed_trading_days >= max_days:
                    log.warning(f"[ZetaTimeStop] #{ticket} {symbol} exceeded time-stop of {max_days} days. Queuing market exit.")
                    state.zeta_status = "TIME_STOP_TRIGGERED"
                    self._queue_time_stop_exit(ticket, symbol, state)

    @staticmethod
    def _count_trading_days(start, end) -> int:
        import numpy as np
        days = np.busday_count(start.date(), end.date(), weekmask="Mon Tue Wed Thu Fri")
        return int(days)

    def _modify_tp_on_broker(self, ticket: int, new_tp: float) -> bool:
        try:
            pos = mt5.position_get(ticket=ticket)
            if not pos: return False
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": pos[0].symbol,
                "sl": pos[0].sl,
                "tp": new_tp
            }
            res = mt5.order_send(request)
            return res.retcode == mt5.TRADE_RETCODE_DONE
        except Exception as exc:
            import logging
            logging.getLogger("CADES.ProfitManager").error(f"[BrokerModify] TP mod failed for #{ticket}: {exc}")
            return False

    def _queue_time_stop_exit(self, ticket: int, symbol: str, state) -> None:
        import logging
        logging.getLogger("CADES.ProfitManager").warning(f"[TimeStop] Executing market exit for #{ticket} {symbol}")
        market_close(mt5.position_get(ticket=ticket)[0], reason="ZETA_TIME_STOP")

    def _emit_tp_gate_reject(self, ticket: int, symbol: str, result: TPValidationResult) -> None:
        import logging
        logging.getLogger("CADES.ProfitManager").error(f"[TP_GATE_REJECT] #{ticket} {symbol}: {result.rejection_reason} | proposed_tp={result.proposed_tp:.5f} rr={result.rr_ratio:.2f}")

    def _emit_tp_adjustment_failure(self, ticket: int, symbol: str, adjusted_tp: float) -> None:
        import logging
        logging.getLogger("CADES.ProfitManager").error(f"[ZetaAdjustFail] Broker TP modification failed for #{ticket} {symbol} -> {adjusted_tp:.5f}.")

    def _apply_time_stop_dampening(self, base_score: float, elapsed_trading_days: int, max_days: int, in_strong_trend: bool) -> float:
        if in_strong_trend or max_days is None: return base_score
        time_consumed = elapsed_trading_days / max_days
        if time_consumed < 0.70: return base_score
        dampening_factor = 1.0 - 0.5 * ((time_consumed - 0.70) / 0.30)
        return base_score * max(0.5, dampening_factor)

    def run_legacy_violation_audit(self) -> dict:
        import logging
        logger = logging.getLogger("CADES.ProfitManager.LegacyAudit")
        logger.info("[LegacyAudit] Starting DIRECTIVE ZETA startup audit...")
        summary = {"total_positions": 0, "violations": [], "compliant": [], "warnings": []}
        for ticket, state in self._states.items():
            summary["total_positions"] += 1
            pos_info = mt5.position_get(ticket=ticket)
            if not pos_info: continue
            audit = self.tp_engine.audit_open_position(
                symbol=state.symbol, entry=state.entry_price, sl=pos_info[0].sl, current_tp=pos_info[0].tp, direction=0 if state.direction == mt5.ORDER_TYPE_BUY else 1
            )
            if not audit.is_valid:
                state.zeta_status = "LEGACY_VIOLATION"
                summary["violations"].append({"ticket": ticket, "symbol": state.symbol, "reason": audit.rejection_reason})
            else:
                state.zeta_status = "COMPLIANT"
                summary["compliant"].append(ticket)
        logger.info(f"[LegacyAudit] Complete: {len(summary['violations'])} violations, {len(summary['compliant'])} compliant.")
        return summary
"""
if 'def _reconcile_tp_compliance(self)' not in code:
    code += methods

# 4. Inject _reconcile_tp_compliance into monitor_loop
if 'self._reconcile_tp_compliance()' not in code:
    code = code.replace("self._cleanup_closed_states(active)", "self._cleanup_closed_states(active)\n        self._reconcile_tp_compliance()")

with open(FILE_PATH, 'w', encoding='utf-8') as f:
    f.write(code)

print("Patch applied to profit_manager_v28_34.py successfully.")