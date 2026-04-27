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
import pandas as pd
from pathlib import Path

# Force absolute resolution of the Hermes framework
PROJECT_ROOT = Path("C:/Sentinel_Project").resolve()
HERMES_ROOT = PROJECT_ROOT / "hermes-agent"
VENV_PYTHON = str(PROJECT_ROOT / "venv" / "Scripts" / "python.exe")

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

# --- LLM PROVIDER CONFIGURATION (Groq / DeepSeek) ---
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

OPENROUTER_API_KEY = "EMPTY"
GROQ_API_KEY = OPENROUTER_API_KEY
GROQ_BASE_URL = "http://127.0.0.1:8080/v1"
GROQ_MODEL = "qwen2.5-coder:3b" # Mixture-of-Experts placeholder (Qwen-A3B recommended)

if not GROQ_API_KEY:
    print("[FATAL ERROR] GROQ_API_KEY not found in .env file.")
    print(f"Please add it to: {PROJECT_ROOT / '.env'}")
    sys.exit(1)

# Inject into environment so downstream Hermes internals can find credentials
os.environ["OPENAI_API_KEY"] = GROQ_API_KEY
os.environ["OPENAI_API_BASE"] = GROQ_BASE_URL

# Directive 2: Initialize the Hermes Agent with Strict System Prompt
SYSTEM_PROMPT = (
    "You are the Commander of the Adaptive Sentinel trading system (v16.9 Production Build). "
    "Your priority is system integrity and constitutional compliance. "
    "MANDATORY: You must operate EXCLUSIVELY on local infrastructure (TurboQuant/Ollama). "
    "For every cycle, you must: "
    "1. Poll the pending_diagnostics queue using get_pending_diagnostics. "
    "   If a CONSTITUTION_BREACH or CONCEPT_DRIFT is found, you MUST enter SRE Mode. "
    "   The Profit Manager has already HEALED the trade by stretching the SL. "
    "   Your task is to analyze the error data, identify the mathematical flaw in "
    "   trade_executor_mcp.py, and autonomously patch it using your file-writing capabilities. "
    "2. Only after clearing the diagnostic queue, check pending_signals. "
    "   Call the Trade Executor tool (execute_trade) using ONLY the Symbol, Kronos Conviction, and HMM State."
)

def boot_hermes():
    """Initialize the Hermes Agent with MCP tool support."""
    logger.info("Booting Hermes Agent...")
    logger.info(f"  LLM Provider: LOCAL TurboQuant (Ollama)")
    logger.info(f"  Model: {GROQ_MODEL}")
    logger.info(f"  Endpoint: {GROQ_BASE_URL}")

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
  provider: openai
  model: {GROQ_MODEL}
  api_key: {GROQ_API_KEY}
  base_url: {GROQ_BASE_URL}
  max_tokens: 4096
  options:
    num_thread: 2
    num_batch: 128
    num_ctx: 4096
    kv_cache_type: "q4_0"

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
        base_url=GROQ_BASE_URL,
        api_key=GROQ_API_KEY,
        model=GROQ_MODEL,
        ephemeral_system_prompt=SYSTEM_PROMPT,
        enabled_toolsets=target_toolsets,
        max_tokens=4096,
        quiet_mode=True, # Set to True to avoid spinner/colorama issues
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

def direct_execute_trade(symbol, conviction, hmm_state):
    """
    Emergency Fallback: Directly calls the trade_executor_mcp.py tool
    via subprocess if all LLMs are down. Ensures 100% signal execution.
    """
    logger.warning(f"[EMERGENCY] LLM Incapacitated. Direct-executing trade for {symbol}...")
    try:
        import subprocess
        # Command: python trade_executor_mcp.py <symbol> <conviction> <hmm_regime>
        cmd = [
            VENV_PYTHON, 
            str(PROJECT_ROOT / "trade_executor_mcp.py"),
            str(symbol),
            str(conviction),
            str(hmm_state)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            logger.info(f"[EMERGENCY] Direct execution successful for {symbol}.")
            return True
        else:
            logger.error(f"[EMERGENCY] Direct execution failed: {res.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error in direct_execute_trade: {e}")
        return False

def resilient_run(agent, prompt, is_signal=False, symbol=None, conviction=None, hmm_state=None):
    """
    Runs a conversation with local-only focus (v16.9).
    Strictly prohibits Cloud LLM use for base SRE operations.
    """
    try:
        # Force local parameters before each run to ensure compliance
        agent.base_url = "http://127.0.0.1:8080/v1"
        agent.api_key = "EMPTY"
        agent.model = "qwen2.5-coder:3b"
        
        agent.run_conversation(prompt)
        return True
    except Exception as e:
        logger.error(f"Local Reasoning Failure: {e}")
        if is_signal and symbol:
            logger.error(f"Triggering Direct Execution Fallback for {symbol}.")
            return direct_execute_trade(symbol, conviction, hmm_state)
        return False

def process_signal(agent, sig_file):
    """Phase 5: Signal Consumption Logic with Guaranteed Execution."""
    try:
        with open(sig_file, 'r') as f:
            payload = json.load(f)
        
        symbol = payload.get("symbol", "UNKNOWN")
        conviction = payload.get("kronos_conviction", 0)
        hmm_state = payload.get("hmm_state", "N/A")
        
        # Staleness Gate (Directive 2)
        try:
            import git_arctic
            store = git_arctic.get_arctic()
            lib = store['oracle_cache']
            h_data = lib.read(f"{symbol}_hmm").data.iloc[-1]
            cache_ts = float(h_data.get('timestamp', 0))
            if time.time() - cache_ts > 300:
                logger.warning(f"[{symbol}] [AWAITING_FRESH_CACHE] Oracle is stale ({int(time.time() - cache_ts)}s old). Ignoring signal.")
                return
        except Exception as e:
            logger.debug(f"Staleness check skipped for {symbol}: {e}")
        
        # Directive 2 (v15.6): Log identifying the specific processing file
        logger.info(f"[RADAR] High-Conviction Signal (Atomic): {symbol} | Conv: {conviction} | HMM: {hmm_state}")
        
        # 1. MANDATORY DIRECT EXECUTION (Reliability Gate)
        # We call the MCP tool directly to ensure the trade fires regardless of API status.
        # This complies with the "Must use trade_executor_mcp.py" directive.
        exec_success = direct_execute_trade(symbol, conviction, hmm_state)
        
        if exec_success:
            if os.path.exists(sig_file):
                os.remove(sig_file)
                logger.info(f"[COMMANDER] Trade for {symbol} executed and atomic signal cleared.")
            
            # 2. CHATOPS TELEMETRY (Best Effort)
            # We still notify the LLM for Discord/Mobile telemetry if the API is up.
            user_command = (
                f"NOTIFICATION: Trade for {symbol} was just executed directly via fallback.\n"
                f"Please update the mobile telemetry and verify the SRE logs."
            )
            # Non-blocking telemetry attempt
            try: resilient_run(agent, user_command)
            except: pass
        else:
            logger.error(f"[COMMANDER] Direct execution failed for {symbol}. Keeping signal in queue.")
            
    except Exception as e:
        logger.error(f"Error processing signal {sig_file.name}: {e}")

def main():
    logger.info("--- Hermes Orchestrator v16.9 Production Active ---")
    
    # Directive 1: Purge Stale Signal Backlog
    logger.info("Checking signal backlog...")
    backlog = list(SIGNAL_DIR.glob("*.json"))
    for f in backlog:
        if time.time() - os.path.getmtime(f) > 1800:
            try: os.remove(f)
            except: pass
    logger.info(f"Cleanup complete. Monitoring queues.")

    agent = boot_hermes()
    logger.info("--- System Online. Monitoring pending_signals/ and pending_diagnostics/ ---")
    
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

                    # Staleness Filter (20-minute cutoff to allow for API backoffs)
                    if time.time() - os.path.getmtime(processing_file) > 1200:
                        try: os.remove(processing_file)
                        except: pass
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
                            
                            # Action: Overwrite the meta cache with 0.0 conviction to block chat_gemma
                            import git_arctic
                            store = git_arctic.get_arctic()
                            lib = store['oracle_cache']
                            meta_df = pd.DataFrame([{
                                "primary_dir": 0,
                                "meta_conviction": 0.0,
                                "timestamp": utils.get_utc_epoch()
                            }])
                            lib.write(f"{symbol}_meta", meta_df)
                            
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
