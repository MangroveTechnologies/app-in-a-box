"""MCP tool definitions.

All tools call the same service layer as REST endpoints.
Three access tiers demonstrated: free (echo), auth (items), x402 (easter_egg).

Each tool registers itself in the discovery catalog (src/mcp/registry.py)
so agents can query /api/v1/docs/tools to discover available tools,
their parameters, access tiers, and pricing before connecting via MCP.
"""
import hashlib
import json
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from src.services.items import create_item, get_item, list_items
from src.services.easter_egg import get_easter_egg
from src.mcp.registry import register_tool, clear_tools, ToolEntry, ToolParam


def register(server: FastMCP):
    """Register all tools on the MCP server and discovery catalog."""
    # Clear catalog to avoid duplicates on re-registration
    clear_tools()

    # -- Free tools --

    @server.tool()
    async def echo(message: str = "") -> str:
        """Echo a message back. Free, no auth required. Use to verify connectivity."""
        result = {
            "echo": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return json.dumps(result)

    register_tool(ToolEntry(
        name="echo",
        description="Echo a message back. Free, no auth required. Use to verify connectivity.",
        access="free",
        parameters=[ToolParam(name="message", type="string", required=False, description="Message to echo back")],
    ))

    # -- Auth-gated tools --

    @server.tool()
    async def items_create(name: str, description: str = "") -> str:
        """Create a new item. Requires API key."""
        item = create_item(name, description)
        return json.dumps(item)

    register_tool(ToolEntry(
        name="items_create",
        description="Create a new item. Requires API key.",
        access="auth",
        parameters=[
            ToolParam(name="name", type="string", required=True, description="Item name"),
            ToolParam(name="description", type="string", required=False, description="Item description"),
        ],
    ))

    @server.tool()
    async def items_list() -> str:
        """List all items. Requires API key."""
        return json.dumps(list_items())

    register_tool(ToolEntry(
        name="items_list",
        description="List all items. Requires API key.",
        access="auth",
        parameters=[],
    ))

    @server.tool()
    async def items_get(item_id: str) -> str:
        """Get an item by ID. Requires API key."""
        item = get_item(item_id)
        if not item:
            return json.dumps({"error": True, "code": "NOT_FOUND", "message": f"Item {item_id} not found"})
        return json.dumps(item)

    register_tool(ToolEntry(
        name="items_get",
        description="Get an item by ID. Requires API key.",
        access="auth",
        parameters=[ToolParam(name="item_id", type="string", required=True, description="UUID of the item")],
    ))

    # -- x402-gated tools --

    @server.tool()
    async def easter_egg() -> str:
        """Get the easter egg message. Costs $0.05 USDC on Base, or free with API key.

        Without payment, returns x402 payment requirements.
        With valid payment or API key, returns the easter egg message.
        """
        result = get_easter_egg()
        return json.dumps(result)

    register_tool(ToolEntry(
        name="easter_egg",
        description="Get the easter egg message. Costs $0.05 USDC on Base, or free with API key.",
        access="x402",
        price="$0.05 USDC",
        network="base",
        parameters=[],
    ))
