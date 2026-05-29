import sys
from unittest.mock import MagicMock

# Mock FastMCP
sys.modules['mcp.server.fastmcp'] = MagicMock()
fast_mcp_mock = MagicMock()
def mock_tool(*args, **kwargs):
    def decorator(func):
        return func
    return decorator
fast_mcp_mock.FastMCP.return_value.tool = mock_tool
sys.modules['mcp.server.fastmcp'].FastMCP = fast_mcp_mock.FastMCP

from agents.hermes_diagnostics_mcp import apply_sre_patch
print("Success!")
