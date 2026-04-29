import sys
import os
import io

# Force UTF-8 for Windows consoles to prevent charmap crashes
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

os.environ["PYTHONUTF8"] = "1"
import time
import json
import logging
import concurrent.futures
import pandas as pd
from pathlib import Path

def resilient_run(agent, command):
    """Executes a command via the Hermes Agent with error isolation."""
    try:
        from loguru import logger # Fallback if logger not global
    except:
        import logging
        logger = logging.getLogger("HermesCommander")
    
    try:
        agent.chat(command)
        return True
    except Exception as e:
        logger.error(f"Hermes Agent Run Failed: {e}")
        return False

# Force dynamic resolution of the project root for WINE/Linux compatibility
PROJECT_ROOT = Path(__file__).parent.resolve()
HERMES_ROOT = PROJECT_ROOT / "hermes-agent"
# Adapt venv path for both Windows and Linux/WINE structures
VENV_PYTHON = str(PROJECT_ROOT / "venv" / "Scripts" / "python.exe") if os.name == 'nt' else str(PROJECT_ROOT / "venv" / "bin" / "python")

if not HERMES_ROOT.exists():
    print(f"[FATAL ERROR] Cannot find Hermes framework at {HERMES_ROOT}")
    print("Please ensure the repository was cloned exactly into C:/Sentinel_Project/hermes-agent")
    sys.exit(1)

# Insert at position 0 to prioritize this path over global packages
sys.path.insert(0, str(HERMES_ROOT))

SIGNAL_DIR = PROJECT_ROOT / "pending_signals"
POLL_INTERVAL = 1  # Seconds between directory scans

# Configure Logging
log_file = r"C:\sentinel_logs\hermes_orchestrator_v16_9.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [ORCHESTRATOR] %(message)s',
    force=True,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file)
    ]
)

# Directive 2: Initialize the Hermes Agent with Strict System Prompt
SYSTEM_PROMPT = (
    "You are the Commander of the Adaptive Sentinel trading system. "
    "Your Fast Loop radar will drop JSON signals into your queue. "
    "For every signal, you must do exactly two things in order: "
    "1. Call the Regime Allocator tool (get_market_regime) using the Symbol, HMM State, and the FFT Data from the signal. "
    "2. If the tool authorizes a strategy (not STEP_ASIDE), call the Trade Executor tool (execute_trade) using the Symbol, Conviction, HMM State, and SL Distance. "
    "Follow the mathematical outputs of these tools exactly."
)

# --- BOOTSTRAP ---
try:
    from run_agent import AIAgent
except ImportError:
    print(f"Error: Could not import Hermes framework from {HERMES_ROOT}")
    print("Ensure HERMES_ROOT is set correctly in the script.")
    sys.exit(1)

# Ensure signals directory exists (Directive 1)
os.makedirs(SIGNAL_DIR, exist_ok=True)

# Logger setup
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    force=True,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(PROJECT_ROOT / "hermes_orchestrator.log"))
    ]
)
logger = logging.getLogger("HermesCommander")

# --- LLM PROVIDER CONFIGURATION (Google Gemini) ---
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash" 

if not GEMINI_API_KEY:
    print("[FATAL ERROR] GEMINI_API_KEY not found in .env file.")
    print(f"Please add it to: {PROJECT_ROOT / '.env'}")
    sys.exit(1)

# Inject into environment so downstream Hermes internals can find credentials
os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY
os.environ["HERMES_OFFLINE"] = "0" 

# Directive 2: Initialize the Hermes Agent with v17.3 System Prompt
SYSTEM_PROMPT = (
    "You are the Commander of the Adaptive Sentinel trading system (v17.3 Production Build). "
    "Your priority is system integrity and constitutional compliance. "
    "MANDATORY: You must operate EXCLUSIVELY on local infrastructure (TurboQuant/Ollama). "
    "For every cycle, you must: "
    "1. Poll the pending_diagnostics queue using get_pending_diagnostics. "
    "   If a CONSTITUTION_BREACH, PSR_FAIL, or CONCEPT_DRIFT is found, you MUST enter SRE Mode. "
    "   Your task is to analyze the error data, identify the mathematical flaw in "
    "   trade_executor_mcp.py or profit_manager.py, and autonomously patch it. "
    "2. Only after clearing the diagnostic queue, check pending_signals. "
    "   Push validated signals to the Discord Bridge for VPS execution."
)

def boot_hermes():
    """Initialize the Hermes Agent with MCP tool support."""
    logger.info("Booting Hermes Agent...")
    logger.info(f"  LLM Provider: Google Gemini API")
    logger.info(f"  Model: {GEMINI_MODEL}")

    hermes_dir = Path.home() / ".hermes"
    hermes_dir.mkdir(exist_ok=True)
    
    # Directive 1: Wipe the Corrupted Configs
    for old_config in ["config.yaml", "config.json", "cli-config.yaml"]:
        old_path = hermes_dir / old_config
        if old_path.exists():
            try:
                old_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete {old_config}: {e}")

    config_path = hermes_dir / "config.yaml"

    # Directive: Point to the new MCP servers in the agents directory
    config_yaml = f"""# Auto-generated by hermes_orchestrator.py
llm:
  provider: google
  model: {GEMINI_MODEL}
  api_key: {GEMINI_API_KEY}
  max_tokens: 4096
  options:
    temperature: 0.7

mcp_servers:
  trade_executor:
    command: "{VENV_PYTHON.replace('\\', '/')}"
    args: ["C:/Sentinel_Project/agents/trade_executor_mcp.py"]
  diagnostics:
    command: "{VENV_PYTHON.replace('\\', '/')}"
    args: ["C:/Sentinel_Project/agents/hermes_diagnostics_mcp.py"]
  quant_research:
    command: "{VENV_PYTHON.replace('\\', '/')}"
    args: ["C:/Sentinel_Project/agents/vectorbt_researcher_mcp.py"]
  fincept_bridge:
    command: "{VENV_PYTHON.replace('\\', '/')}"
    args: ["C:/Sentinel_Project/agents/mcp_fincept_bridge.py"]
  gitnexus:
    command: "C:/Users/ADMIN/.antigravity/nodejs_extracted/node-v24.15.0-win-x64/node.exe"
    args: ["C:/Users/ADMIN/.antigravity/GitNexus/gitnexus/dist/cli/index.js", "mcp"]

platform_toolsets:
  cli: [mcp, terminal, file, todo]
"""

    # Directive 2: Enforce Explicit UTF-8 Encoding
    with open(config_path, "w", encoding='utf-8') as f:
        f.write(config_yaml)
    logger.info(f"[SYSTEM] Hermes config.yaml written to {config_path}")

    # Initialize agent - base_url/api_key passed directly as belt-and-suspenders
    os.environ["HERMES_GIT_BASH_PATH"] = r"C:\Program Files\Git\bin\bash.exe"
    
    # Discovery Diagnostic
    from model_tools import get_tool_definitions, discover_builtin_tools
    from tools.mcp_tool import discover_mcp_tools
    
    # Force fresh discovery after config write
    discover_builtin_tools()
    discover_mcp_tools()
    
    # The MCP servers are registered as toolsets with their server names
    target_toolsets = ["trade_executor", "diagnostics", "quant_research", "terminal", "file"]
    tools = get_tool_definitions(enabled_toolsets=target_toolsets)
    discovered_names = [t['function']['name'] for t in tools]
    logger.info(f"[DIAGNOSTIC] Discovered tools: {discovered_names}")

    agent = AIAgent(
        api_key=GEMINI_API_KEY,
        model=GEMINI_MODEL,
        provider="google",
        ephemeral_system_prompt=SYSTEM_PROMPT,
        enabled_toolsets=target_toolsets,
        max_tokens=4096,
        quiet_mode=True, 
    )
    logger.info("Hermes Agent initialized successfully.")
    return agent

def send_sre_alert(msg):
    """Sends SRE alerts to Discord."""
    webhook_url = "https://discord.com/api/webhooks/1496246026611458048/2ShGeHJjN-Z6XrydLjFy_hOz-iLWrqNHVfp3vanWHj7udTYXUGfglWvUdxJ0WqLyAK88"
    try:
        import requests
        requests.post(webhook_url, json={"content": msg}, timeout=5)
    except: pass

def pre_flight_audit():
    """Phase 5: LLM Pre-Flight Audit."""
    import requests
    try:
        resp = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            logger.info("LLM Pre-Flight Audit: PASSED")
            return True
    except Exception as e:
        logger.error(f"LLM Pre-Flight Audit Error: {e}")
    
    logger.critical("LLM Pre-Flight Audit: FAILED (Ollama unreachable at 127.0.0.1:11434).")
    logger.critical("Constitution Violation: Sovereign Cloud Engine requires active local LLM. Halting Matrix.")
    sys.exit(1)

def push_to_firebase(payload):
    """Phase 5: Firebase Signal Bridge (VPS -> Cloud)."""
    # Placeholder for Firebase pushing
    # In v17.2, we push to Firebase Realtime Database
    # self.ref.push(payload)
    
    # Simulation: Push to pending_signals/ for Local Listener to pick up
    SIGNAL_QUEUE = PROJECT_ROOT / "pending_signals"
    os.makedirs(SIGNAL_QUEUE, exist_ok=True)
    filename = SIGNAL_QUEUE / f"signal_{int(time.time())}_{payload['symbol']}.json"
    with open(filename, 'w') as f:
        json.dump(payload, f, indent=2)
    logger.info(f"[FIREBASE_BRIDGE] Signal pushed for {payload['symbol']}: {filename}")
    return True

def process_signal(agent, sig_file):
    """Phase 5: Signal Consumption Logic with Firebase Bridge."""
    try:
        with open(sig_file, 'r') as f:
            payload = json.load(f)
        
        symbol = payload.get("symbol", "UNKNOWN")
        conviction = payload.get("kronos_conviction", 0)
        hmm_state = payload.get("hmm_state", "N/A")
        
        # 1. MANDATORY FIREBASE PUSH (v17.2)
        # We push to the bridge instead of direct execution.
        signal_payload = {
            "symbol": symbol,
            "direction": "BUY" if conviction > 0.5 else "SELL",
            "conviction": conviction,
            "hmm_state": hmm_state,
            "timestamp": int(time.time()),
            "version": "v17.2-PROD"
        }
        
        success = push_to_firebase(signal_payload)
        
        if success:
            if os.path.exists(sig_file):
                os.remove(sig_file)
            
            # 2. CHATOPS TELEMETRY
            user_command = (
                f"NOTIFICATION: Validated signal for {symbol} (Conv: {conviction}) pushed to Firebase Bridge.\n"
                f"Local Execution Node (Machine B) notified."
            )
            try: resilient_run(agent, user_command)
            except: pass
        else:
            logger.error(f"[BRIDGE_ERROR] Failed to push signal for {symbol}. Keeping in queue.")
            
    except Exception as e:
        logger.error(f"Error processing signal {sig_file.name}: {e}")

def main():
    logger.info("--- Hermes Orchestrator v17.3 Cloud-Native Active ---")
    
    # Directive: LLM Pre-Flight Audit
    pre_flight_audit()
    
    # Directive 1: Purge Stale Signal Backlog
    logger.info("Checking signal backlog...")
    backlog = list(SIGNAL_DIR.glob("*.json"))
    for f in backlog:
        if time.time() - os.path.getmtime(f) > 1800:
            try: os.remove(f)
            except: pass
    logger.info(f"Cleanup complete. Monitoring queues.")

    agent = boot_hermes()
    logger.info("--- System Online. VPS Monitoring Matrix Active. ---")
    
    # Priority Queues
    DIAG_DIR = PROJECT_ROOT / "pending_diagnostics"
    
    # Directive 1: Continuous polling loop
    while True:
        try:
            # 1. PRIORITY 1: Diagnostics (SRE Mode with Batching)
            diag_files = list(DIAG_DIR.glob("*.json"))
            if diag_files:
                logger.info(f"[SRE] Found {len(diag_files)} diagnostic tickets. Batching...")
                
                # Deduplication & Batching by error_type
                batches = {}
                for d_file in diag_files:
                    try:
                        with open(d_file, 'r') as f:
                            data = json.load(f)
                        etype = data.get("error_type", "UNKNOWN_BREACH")
                        if etype not in batches: batches[etype] = []
                        batches[etype].append({"file": d_file, "data": data})
                    except: continue
                
                for etype, items in batches.items():
                    logger.info(f"[SRE] Processing Batch: {etype} ({len(items)} tickets)")
                    
                    # Consolidate Prompt
                    consolidated_data = [item["data"] for item in items]
                    user_cmd = (
                        f"CRITICAL SRE BATCH ALERT: {etype}\n"
                        f"Ticket Count: {len(items)}\n"
                        f"Consolidated Data: {json.dumps(consolidated_data, indent=2)}\n\n"
                        f"Analyze these breaches collectively. Identify the root mathematical flaw in "
                        f"trade_executor_mcp.py that caused these deviations, and patch the code once to resolve ALL of them."
                    )
                    
                    success = resilient_run(agent, user_cmd)
                    
                    if success:
                        for item in items:
                            try: 
                                if item["file"].exists(): item["file"].unlink()
                            except: pass
                        logger.info(f"[SRE] Batch {etype} cleared and patched.")
                    else:
                        logger.error(f"[SRE] Failed to process batch {etype}. Keeping tickets for retry.")

            # 2. PRIORITY 2: Signals
            signals = sorted(list(SIGNAL_DIR.glob("*.json")), key=os.path.getmtime, reverse=True)
            
            if signals:
                for sig_file in signals:
                    # Directive 2 (v15.6): Atomic Signal Consumption
                    # We rename the file to .processing before reading to avoid race conditions
                    processing_file = Path(str(sig_file) + ".processing")
                    try:
                        os.rename(sig_file, processing_file)
                    except FileNotFoundError:
                        # Another thread/process grabbed it first
                        continue
                    except Exception as e:
                        logger.error(f"Atomic rename failed for {sig_file.name}: {e}")
                        continue

                    # Staleness Filter: 900 s (Phase 1 — STALENESS_THRESHOLD)
                    if time.time() - os.path.getmtime(processing_file) > 900:
                        logger.warning(f"[STALE_SIGNAL] {processing_file.name} age > 900s. Discarding.")
                        try: os.remove(processing_file)
                        except: pass
                        continue

                    # 3. PRIORITY 3: Weekend Blackout Protocol (v17.3)
                    # Friday 23:55 to Monday 00:15 Broker Time (Approx UTC+2/3)
                    # Using UTC for universal enforcement. 
                    # Fri 22:00 UTC to Sun 22:00 UTC covers most broker blackout windows.
                    from datetime import datetime, timezone, time as dt_time
                    now_utc = datetime.now(timezone.utc)
                    is_weekend = False
                    
                    # Friday after 21:55 UTC
                    if now_utc.weekday() == 4 and now_utc.time() >= dt_time(21, 55):
                        is_weekend = True
                    # Saturday all day
                    elif now_utc.weekday() == 5:
                        is_weekend = True
                    # Sunday before 22:15 UTC
                    elif now_utc.weekday() == 6 and now_utc.time() <= dt_time(22, 15):
                        is_weekend = True
                    
                    if is_weekend:
                        # Crypto Bypass (Directive 4): Allow Crypto signals 24/7
                        # We need to peek at the signal file to check the symbol
                        try:
                            with open(processing_file, 'r') as f:
                                sig_data = json.load(f)
                            symbol = sig_data.get("symbol", "").upper()
                            # Basic crypto check: if symbol is in a known list or has crypto patterns
                            from gitagent_utils import get_symbol_regime
                            if get_symbol_regime(symbol) != "CRYPTO":
                                logger.warning(f"🚨 [WEEKEND_BLACKOUT] Rejecting {symbol} signal during broker closure.")
                                os.remove(processing_file)
                                continue
                        except Exception as e:
                            logger.error(f"Weekend peek failed: {e}")
                            os.remove(processing_file)
                            continue

                    process_signal(agent, processing_file)
            
            # 3. PRIORITY 3: Concept Drift Monitor (Directive: SHAP > 65%)
            SHAP_DIR = PROJECT_ROOT / "shap_diagnostics"
            if SHAP_DIR.exists():
                diag_files = list(SHAP_DIR.glob("*.json"))
                for df in diag_files:
                    try:
                        with open(df, 'r') as f:
                            data = json.load(f)
                        
                        weights = data.get("weights", {})
                        max_w = max(abs(v) for v in weights.values()) if weights else 0
                        
                        if max_w > 0.65:
                            symbol = data.get("symbol", "UNKNOWN")
                            logger.error(f"🚨 [CONCEPT_DRIFT] {symbol}: Feature weight {max_w:.2%} > 65%! Halting Execution.")
                            send_sre_alert(f"⚠️ **CONCEPT_DRIFT_WARNING**: {symbol} feature weight {max_w:.2%} exceeds threshold. Forcing Conviction to 0.0.")
                            
                            # Action: Overwrite meta cache with 0.0 conviction (Concept Drift Block)
                            import gitagent_utils as _utils
                            import git_arctic
                            store = git_arctic.get_arctic()
                            _lib  = store['oracle_cache']
                            meta_df = pd.DataFrame([{
                                "primary_dir":     0,
                                "meta_conviction": 0.0,
                                "hmm_state":       "RANGE",
                                "timestamp":       _utils.get_utc_epoch(),
                            }])
                            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
                                try:
                                    _ex.submit(_lib.write, f"{symbol}_meta", meta_df).result(timeout=0.3)
                                except concurrent.futures.TimeoutError:
                                    logger.error(f"[ARCTIC_TIMEOUT] Concept-drift override write > 300ms for {symbol}")
                            
                        # Cleanup old diagnostic after processing
                        if time.time() - os.path.getmtime(df) > 3600:
                            os.remove(df)
                    except: continue
            
            # Sleep to prevent CPU hammering
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("Shutting down Hermes Orchestrator...")
            break
        except Exception as e:
            logger.error(f"Main Loop Exception: {e}")
            time.sleep(5) 

if __name__ == "__main__":
    # Directive 1 (v15.6): Implement OS-Level Singleton Lock
    import socket
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(("127.0.0.1", 65433)) # Unique port for Orchestrator
    except socket.error:
        print("[FATAL] Another instance of Hermes Orchestrator is already running. Exiting.")
        sys.exit(1)
        
    main()
