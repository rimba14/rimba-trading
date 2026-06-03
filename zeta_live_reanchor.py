import MetaTrader5 as mt5
import logging
from tp_placement_engine import TPPlacementEngine, StructuralLevelResolver
from profit_manager_v28_34 import OracleCache
from fastapi_sniper import execute_exit
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ZetaReanchor")

def reanchor_all():
    if not mt5.initialize():
        logger.error(f"MT5 Init failed, error code: {mt5.last_error()}")
        return

    logger.info("Starting ZETA live re-alignment...")
    
    oracle = OracleCache(ttl=300)
    level_resolver = StructuralLevelResolver(oracle)
    engine = TPPlacementEngine(oracle, level_resolver)

    positions = mt5.positions_get()
    if positions is None:
        logger.error("No positions found or error getting positions.")
        mt5.shutdown()
        return

    for pos in positions:
        direction = 1 if pos.type == mt5.ORDER_TYPE_BUY else -1
        
        logger.info(f"Auditing #{pos.ticket} {pos.symbol} (TP={pos.tp})")
        audit = engine.audit_open_position(
            symbol=pos.symbol,
            entry=pos.price_open,
            sl=pos.sl,
            current_tp=pos.tp,
            direction=direction
        )

        if not audit.is_valid:
            if "CRYPTO" in (audit.rejection_reason or "").upper() or audit.asset_class.name == "CRYPTO":
                logger.warning(f"#{pos.ticket} {pos.symbol} failed ZETA crypto veto. Executing market close.")
                execute_exit(pos.ticket, pos.symbol, "ZETA_CRYPTO_VETO")
            else:
                logger.warning(f"#{pos.ticket} {pos.symbol} failed ZETA validation: {audit.rejection_reason}")
                
                # We need to use validate_tp_placement to get a structural TP if possible
                val = engine.validate_tp_placement(
                    symbol=pos.symbol,
                    entry=pos.price_open,
                    sl=pos.sl,
                    proposed_tp=pos.tp,
                    direction=direction,
                    use_structural_resolver=True
                )
                
                # For legacy positions, even if it fails Law 5 RR gate, we MUST re-anchor the TP!
                new_tp = None
                if val.structural_level:
                    new_tp = val.structural_level.price
                elif val.binding_ceiling_price:
                    new_tp = val.binding_ceiling_price
                
                if new_tp:
                    logger.info(f"Force re-anchoring #{pos.ticket} {pos.symbol} TP to {new_tp:.5f} (was {pos.tp})")
                    
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": pos.symbol,
                        "sl": pos.sl,
                        "tp": new_tp
                    }
                    res = mt5.order_send(request)
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info(f"#{pos.ticket} {pos.symbol} re-anchored successfully.")
                    else:
                        logger.error(f"#{pos.ticket} {pos.symbol} re-anchor failed: {res.retcode if res else 'None'}")
                else:
                    logger.warning(f"#{pos.ticket} {pos.symbol} could not resolve a fallback TP!")
        else:
            logger.info(f"#{pos.ticket} {pos.symbol} is already compliant.")

    mt5.shutdown()
    logger.info("ZETA live re-alignment complete.")

if __name__ == "__main__":
    reanchor_all()
