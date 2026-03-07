"""MCP server -- unified entry point for all agent tools.

Mounted at /mcp on the FastAPI app via Streamable HTTP transport.
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gcp-app-template")


def create_mcp_server() -> FastMCP:
    """Create and configure the MCP server with all tools registered."""
    from src.mcp.tools import register
    register(mcp)
    return mcp
