import sys
import logging

def get_logger(name: str) -> logging.Logger:
    # Rule 4: Universal UTF-8 Enforcement
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except:
            pass
            
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler(
            open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
        )
        h.setFormatter(logging.Formatter(
            '%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s'
        ))
        logger.addHandler(h)
    return logger
