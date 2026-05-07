"""
sre_heal_db.py - SRE Database Healer (v21.0)
Directive 3: Purge corrupted ArcticDB/Parquet files for USDJPY.
The feeder will re-initialize clean files on its next cycle.

Usage: python sre_heal_db.py
Safe to re-run: idempotent, will report if files already absent.
"""
import os
import shutil
import pathlib
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SRE_HEAL] %(message)s",
)

# ---------------------------------------------------------------------------
# TARGET PATHS — Corrupted USDJPY files identified via feeder_production.log
# Error: "Parquet magic bytes not found in footer" — file structure corrupted.
# ---------------------------------------------------------------------------
ARCTIC_DB_ROOT = pathlib.Path(r"C:\Sentinel_Project\arctic_db")

# Specific confirmed corrupt files (from feeder_production.log audit)
CORRUPT_FILES = [
    ARCTIC_DB_ROOT / "trading_data" / "USDJPY_M1.parquet",
    ARCTIC_DB_ROOT / "trading_data" / "USDJPY_TICKS.parquet",
]

# Glob patterns to catch any shards we may have missed
USDJPY_PATTERNS = [
    ARCTIC_DB_ROOT / "trading_data",   # Search this dir for USDJPY files
    ARCTIC_DB_ROOT,                     # Also scan root level
]


def find_usdjpy_files() -> list:
    """Scan all ArcticDB subdirectories for any USDJPY-related files.
    Uses a resolved-path set to deduplicate results from overlapping globs.
    """
    seen: set = set()
    found: list = []
    for search_path in USDJPY_PATTERNS:
        if search_path.exists():
            for p in search_path.rglob("*USDJPY*"):
                if p.is_file():
                    resolved = p.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        found.append(p)
    return found


def heal():
    logging.info("=" * 60)
    logging.info("SENTINEL SRE DATABASE HEALER (v21.0)")
    logging.info("Target: Corrupted USDJPY Parquet files")
    logging.info("=" * 60)

    # Phase 1: Find all USDJPY files
    all_usdjpy = find_usdjpy_files()

    if not all_usdjpy:
        logging.info("[SCAN] No USDJPY files found in arctic_db. Nothing to purge.")
        logging.info("[OK] Database is already clean. Feeder will create fresh files on next cycle.")
        return

    logging.info(f"[SCAN] Found {len(all_usdjpy)} USDJPY file(s):")
    for f in all_usdjpy:
        size_kb = f.stat().st_size / 1024
        logging.info(f"  - {f.relative_to(ARCTIC_DB_ROOT)} ({size_kb:.1f} KB)")

    # Phase 2: Create a backup timestamp
    ts = int(time.time())
    backup_dir = ARCTIC_DB_ROOT / f"_sre_backup_{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    logging.info(f"\n[BACKUP] Copying files to {backup_dir.name} before deletion...")

    backed_up = []
    for f in all_usdjpy:
        try:
            dest = backup_dir / f.name
            shutil.copy2(f, dest)
            backed_up.append(f)
            logging.info(f"  [BACKUP OK] {f.name} -> {dest}")
        except Exception as e:
            logging.error(f"  [BACKUP FAIL] {f.name}: {e}")

    # Phase 3: Delete corrupt files
    logging.info(f"\n[PURGE] Deleting {len(backed_up)} corrupt USDJPY file(s)...")
    purged = 0
    failed = 0
    for f in backed_up:
        try:
            f.unlink()
            logging.info(f"  [DELETED] {f.name}")
            purged += 1
        except Exception as e:
            logging.error(f"  [DELETE FAIL] {f.name}: {e}")
            failed += 1

    # Phase 4: Summary
    logging.info("\n" + "=" * 60)
    logging.info("[SUMMARY]")
    logging.info(f"  Files found:   {len(all_usdjpy)}")
    logging.info(f"  Files purged:  {purged}")
    logging.info(f"  Failed:        {failed}")
    logging.info(f"  Backup stored: {backup_dir}")
    logging.info("=" * 60)

    if failed == 0:
        logging.info("[SUCCESS] USDJPY corruption cleared.")
        logging.info("[NEXT STEP] Restart feeder_production.py — it will auto-create")
        logging.info("            fresh, valid Parquet files on the next tick cycle.")
    else:
        logging.warning("[PARTIAL] Some files could not be deleted. Check permissions.")
        logging.warning("          Close any processes holding file handles and re-run.")


if __name__ == "__main__":
    heal()
