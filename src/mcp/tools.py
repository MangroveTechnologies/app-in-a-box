"""MCP tool definitions.

All tools call the same service layer as REST endpoints.
Three access tiers demonstrated: free (echo), auth (items), x402 (easter_egg).
"""
import hashlib
import json
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from src.services.items import create_item, get_item, list_items
from src.services.easter_egg import get_easter_egg
from src.shared.x402.config import (
    EASTER_EGG_PRICE, EASTER_EGG_DESCRIPTION,
    FACILITATOR_URL, NETWORK, PAY_TO, USDC_BASE,
)
from src.shared.x402.models import PaymentOption, PaymentRequirements


def register(server: FastMCP):
    """Register all tools on the MCP server."""

    @server.tool()
    async def echo(message: str = "") -> str:
        """Echo a message back. Free, no auth required. Use to verify connectivity."""
        result = {
            "echo": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return json.dumps(result)

    @server.tool()
    async def items_create(name: str, description: str = "") -> str:
        """Create a new item. Requires API key."""
        item = create_item(name, description)
        return json.dumps(item)

    @server.tool()
    async def items_list() -> str:
        """List all items. Requires API key."""
        return json.dumps(list_items())

    @server.tool()
    async def items_get(item_id: str) -> str:
        """Get an item by ID. Requires API key."""
        item = get_item(item_id)
        if not item:
            return json.dumps({"error": True, "code": "NOT_FOUND", "message": f"Item {item_id} not found"})
        return json.dumps(item)

    @server.tool()
    async def easter_egg() -> str:
        """Get the easter egg message. Costs $0.05 USDC on Base, or free with API key.

        Without payment, returns x402 payment requirements.
        With valid payment or API key, returns the easter egg message.
        """
        # Note: x402 payment flow for MCP is handled at the HTTP transport layer.
        # When accessed via MCP Streamable HTTP, the same x402 middleware applies.
        # This tool returns the result directly; payment enforcement is at the transport level.
        result = get_easter_egg()
        return json.dumps(result)
