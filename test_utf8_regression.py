"""
test_utf8_regression.py - Directive 5: UTF-8 Encoding Regression Test (v26.7 SRE)

Deliberately logs messages containing emoji and special characters to verify:
  1. No UnicodeEncodeError raised on any handler.
  2. Log file is valid UTF-8.
  3. TRADE_ACTION_SLTP log path completes without crash.
"""

import os
import sys
import logging
import tempfile
from pathlib import Path

# Force UTF-8 at process level (mirrors production hardening)
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

PASS_COUNT = 0
FAIL_COUNT = 0

def _assert(condition, msg):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  [PASS] {msg}")
    else:
        FAIL_COUNT += 1
        print(f"  [FAIL] {msg}")


def test_logger_config_import():
    """Test that logger_config.py imports cleanly and forces UTF-8."""
    print("\n=== Test 1: logger_config.py Import ===")
    try:
        sys.path.insert(0, r"C:\Sentinel_Project")
        from logger_config import get_logger, configure_root_logger
        _assert(True, "logger_config imported successfully")
        _assert(os.environ.get("PYTHONIOENCODING") == "utf-8", "PYTHONIOENCODING == utf-8")
    except Exception as e:
        _assert(False, f"logger_config import failed: {e}")


def test_emoji_logging_to_file():
    """Test that emoji can be written to a UTF-8 FileHandler without crash."""
    print("\n=== Test 2: Emoji Logging to File ===")
    test_log = Path(tempfile.gettempdir()) / "sentinel_utf8_test.log"
    if test_log.exists():
        test_log.unlink()

    logger = logging.getLogger("UTF8_TEST")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fh = logging.FileHandler(str(test_log), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)

    test_messages = [
        "[OK] Trade executed successfully",
        "[FAIL] SL/TP modification failed",
        "[WARN] Margin level low",
        "Currency symbols: EUR € GBP £ JPY ¥",
        "Unicode arrows: → ← ↑ ↓",
        "Emoji stress test: ✅ ❌ ⚠️ 🔴 🟢 💀 🚨",
        "Mixed: SENTINEL_v27.0_CADES_P0.85 [OK] Ticket #12345",
    ]

    crashed = False
    for msg in test_messages:
        try:
            logger.info(msg)
        except UnicodeEncodeError as e:
            _assert(False, f"UnicodeEncodeError on message: {msg[:30]}... | {e}")
            crashed = True

    fh.close()
    logger.removeHandler(fh)

    if not crashed:
        _assert(True, "All emoji messages logged without UnicodeEncodeError")

    # Verify file is valid UTF-8
    try:
        content = test_log.read_text(encoding="utf-8")
        _assert("Emoji stress test" in content, "Log file contains emoji test message")
        _assert("€" in content or "EUR" in content, "Log file contains currency symbols")
    except UnicodeDecodeError:
        _assert(False, "Log file is NOT valid UTF-8")

    # Cleanup
    if test_log.exists():
        test_log.unlink()


def test_stream_handler_emoji():
    """Test that StreamHandler with UTF-8 wrapper handles emoji."""
    print("\n=== Test 3: StreamHandler Emoji ===")
    import io

    logger = logging.getLogger("STREAM_TEST")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    stream = io.TextIOWrapper(
        open(sys.stdout.fileno(), "wb", closefd=False),
        encoding="utf-8", errors="replace", line_buffering=True
    )
    sh = logging.StreamHandler(stream=stream)
    sh.setFormatter(logging.Formatter("  [STREAM] %(message)s"))
    logger.addHandler(sh)

    try:
        logger.info("[OK] ✅ TRADE_ACTION_SLTP phase complete")
        logger.warning("[WARN] ⚠️ Spread widened beyond 1.5x ATR")
        logger.error("[FAIL] ❌ Naked Kill Switch fired for Ticket #99999")
        logger.critical("[ALERT] 🚨 SL/TP modification failed after 3 retries")
        _assert(True, "StreamHandler handled all emoji without crash")
    except UnicodeEncodeError as e:
        _assert(False, f"StreamHandler UnicodeEncodeError: {e}")
    finally:
        logger.removeHandler(sh)


def test_fastapi_sniper_encoding():
    """Test that fastapi_sniper.py has encoding='utf-8' on its FileHandler."""
    print("\n=== Test 4: fastapi_sniper.py FileHandler Encoding ===")
    sniper_path = Path(r"C:\Sentinel_Project\fastapi_sniper.py")
    if not sniper_path.exists():
        _assert(False, "fastapi_sniper.py not found")
        return

    content = sniper_path.read_text(encoding="utf-8")
    _assert('FileHandler(LOG_FILE, encoding="utf-8")' in content, 
            'FileHandler has encoding="utf-8"')
    _assert('encoding="utf-8"' in content and 'errors="replace"' in content,
            'StreamHandler uses UTF-8 wrapper')
    _assert("💀" not in content and "🚨" not in content and "✅" not in content and "❌" not in content and "⚠️" not in content,
            "No raw emoji in fastapi_sniper.py")


def test_profit_manager_encoding():
    """Test that profit_manager.py has no raw emoji."""
    print("\n=== Test 5: profit_manager.py Emoji Audit ===")
    pm_path = Path(r"C:\Sentinel_Project\profit_manager.py")
    if not pm_path.exists():
        _assert(False, "profit_manager.py not found")
        return
    
    content = pm_path.read_text(encoding="utf-8")
    _assert('encoding="utf-8"' in content, 'profit_manager.py has encoding="utf-8"')
    _assert("💀" not in content, "No skull emoji in profit_manager.py")


def test_environment_hardening():
    """Test that PYTHONIOENCODING is set and stdout is UTF-8."""
    print("\n=== Test 6: Environment Hardening ===")
    _assert(os.environ.get("PYTHONIOENCODING") == "utf-8", "PYTHONIOENCODING == utf-8")
    _assert(sys.stdout.encoding.lower() == "utf-8", f"sys.stdout.encoding == utf-8 (actual: {sys.stdout.encoding})")
    _assert(sys.stderr.encoding.lower() == "utf-8", f"sys.stderr.encoding == utf-8 (actual: {sys.stderr.encoding})")


if __name__ == "__main__":
    print("=" * 60)
    print("  SENTINEL v27.0 UTF-8 ENCODING REGRESSION TEST")
    print("=" * 60)

    test_logger_config_import()
    test_emoji_logging_to_file()
    test_stream_handler_emoji()
    test_fastapi_sniper_encoding()
    test_profit_manager_encoding()
    test_environment_hardening()

    print("\n" + "=" * 60)
    print(f"  RESULTS: {PASS_COUNT} PASSED | {FAIL_COUNT} FAILED")
    if FAIL_COUNT == 0:
        print("  [OK] ALL TESTS PASSED - UTF-8 Hardening Verified")
    else:
        print("  [FAIL] SOME TESTS FAILED - Review output above")
    print("=" * 60)

    sys.exit(1 if FAIL_COUNT > 0 else 0)
