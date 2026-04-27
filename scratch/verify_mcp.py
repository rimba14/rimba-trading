import sys
import os
from pathlib import Path

PROJECT_ROOT = Path("C:/Sentinel_Project").resolve()
HERMES_ROOT = PROJECT_ROOT / "hermes-agent"
sys.path.insert(0, str(HERMES_ROOT))

from model_tools import get_tool_definitions

try:
    tools = get_tool_definitions(enabled_toolsets=["mcp"])
    print(f"Discovered MCP tools: {[t['function']['name'] for t in tools]}")
except Exception as e:
    print(f"Discovery Error: {e}")
