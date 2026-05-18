import sys
import os
from pathlib import Path
import MetaTrader5 as mt5

def run_preflight():
    print("========================================")
    print("   SENTINEL CANONICAL BOOT PREFLIGHT")
    print("========================================")
    
    # 1. Version Manifest Audit
    try:
        from sentinel.version_manifest import AGENT_SIGNATURE, LEGACY_BANNED
        print(f"[OK] Manifest Loaded: {AGENT_SIGNATURE}")
    except Exception as e:
        print(f"[FAIL] Failed to load version manifest: {e}")
        sys.exit(1)
        
    for banned in LEGACY_BANNED:
        if banned in AGENT_SIGNATURE:
            print(f"[ABORT] Legacy version signature breach detected: {banned}")
            sys.exit(1)
    print("[OK] Version verification passed (No legacy ghost).")
    
    # 2. Output Encoding Check
    try:
        if getattr(sys.stdout, 'encoding', '').lower().replace('-', '') != 'utf8':
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        import io
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass
            
    enc = getattr(sys.stdout, 'encoding', '') or ''
    if enc.lower().replace('-', '') != 'utf8':
        print(f"[ABORT] Output encoding is not UTF-8: {enc}")
        sys.exit(1)
    print("[OK] UTF-8 stdout encoding confirmed.")
    
    # 3. MT5 Initialization & Demo Lock (Paper Mode Check)
    if not mt5.initialize():
        print("[FAIL] MetaTrader5 initialization failed!")
        sys.exit(1)
        
    acc = mt5.account_info()
    if not acc:
        print("[FAIL] Failed to fetch MT5 account info!")
        sys.exit(1)
        
    print(f"[OK] MT5 Terminal Connected. Login: {acc.login} | Server: {acc.server}")
    
    # Check for Paper Mode (Demo Account Lock)
    is_paper_mode_requested = os.environ.get("SENTINEL_PAPER_MODE") == "1" or "--papermode" in [a.lower() for a in sys.argv]
    is_demo = (acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO) or ("DEMO" in acc.server.upper())
    
    if is_paper_mode_requested:
        if not is_demo:
            print("[ABORT] CATASTROPHIC GUARD: Paper Mode requested but MT5 is connected to a LIVE/REAL account!")
            sys.exit(1)
        print("[OK] Controlled Burn Verified: System locked to DEMO/PAPER account.")
    else:
        if is_demo:
            print("[WARNING] No Paper Mode flag specified, but MT5 is connected to a Demo account.")
            
    # 4. Self Certification Suite
    print("[PREFLIGHT] Running Self-Certification Suite...")
    try:
        import self_cert
        self_cert.run_self_cert()
        print("[OK] Self-Certification passed successfully.")
    except Exception as e:
        print(f"[FAIL] Self-Certification exception: {e}")
        sys.exit(1)
        
    print("[PASS] Sentinel preflight health gate cleared successfully!")

if __name__ == "__main__":
    run_preflight()
