"""MCP server -- unified entry point for all agent tools.

Mounted at /mcp on the FastAPI app via Streamable HTTP transport.
"""
from mcp.server.fastmcp import FastMCP

_mcp_server = None


def create_mcp_server() -> FastMCP:
    """Create and configure the MCP server with all tools registered.

    Idempotent -- returns the same server instance on repeated calls
    to avoid duplicate tool registration warnings.
    """
    global _mcp_server
    if _mcp_server is not None:
        return _mcp_server

    _mcp_server = FastMCP("app-in-a-box")

    from src.mcp.tools import register
    register(_mcp_server)

    return _mcp_server
