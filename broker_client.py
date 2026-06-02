import MetaTrader5 as mt5
import logging
from gitagent_types import ExecutionPermit

logger = logging.getLogger("BrokerClient")

def dispatch_permit(permit: ExecutionPermit):
    """
    Synchronous Broker Gateway.
    Strictly requires a mathematically verified ExecutionPermit.
    It absolutely abstracts away mt5.order_send from the Action Layer.
    """
    if not permit.is_valid:
        logger.error(f"[BROKER_GATEWAY] ABORTING THREAD: ExecutionPermit is INVALID. Reason: {permit.rejection_reason}")
        return None

    if not permit.request_dict:
        logger.error("[BROKER_GATEWAY] ABORTING THREAD: ExecutionPermit missing request dictionary.")
        return None

    # Final physical dispatch
    res = mt5.order_send(permit.request_dict)
    
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"[BROKER_GATEWAY] Dispatch Success: Order #{res.order} executed for {permit.request_dict.get('symbol')}.")
    else:
        code = res.retcode if res else "No response"
        logger.warning(f"[BROKER_GATEWAY] Dispatch Failed for {permit.request_dict.get('symbol')}. MT5 Code: {code}")

    return res
