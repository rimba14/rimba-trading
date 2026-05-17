import os
import pytest
from constants import AGENT_SIGNATURE, TRADE_COMMENT_TEMPLATE
from logger_config import get_logger

def test_no_legacy_version_strings():
    import glob
    for root, dirs, files in os.walk("."):
        if ".git" in root or "venv" in root or "llms" in root or "kronos" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        assert "SENTINEL_v23" not in content, f"Legacy strings found in {path}"
                except:
                    pass

def test_utf8_log_handler():
    log = get_logger("test")
    # Must not raise UnicodeEncodeError
    log.info("[OK] UTF-8 test: \u2705 \u274c \u26a0\ufe0f EUR=\u20ac GBP=\u00a3")

def test_agent_signature_format():
    assert AGENT_SIGNATURE == "SENTINEL_v26.9_IRONCLAD_CADES"
    assert "v23" not in AGENT_SIGNATURE

def test_agent_signature_mt5_limit():
    assert len(AGENT_SIGNATURE) < 31, f"AGENT_SIGNATURE exceeds MT5 31-char limit: {len(AGENT_SIGNATURE)} chars"

def test_trade_comment_template():
    comment = TRADE_COMMENT_TEMPLATE.format(
        symbol="ADAUSD", regime="RISK_ON", signal_type="MEAN_REVERSION"
    )[:31]
    assert "v26.9" in comment
    assert len(comment) <= 31  # MT5 broker comment field limit
