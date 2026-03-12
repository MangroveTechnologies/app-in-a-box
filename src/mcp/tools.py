"""MCP tool definitions with auth and x402 payment enforcement.

All tools call the same service layer as REST endpoints.
Three access tiers demonstrated: free (echo), auth (items), x402 (easter_egg).

Auth-gated tools require a valid API key passed as the `api_key` parameter.
x402-gated tools require either a valid API key OR a signed x402 payment
passed as a base64-encoded `payment` parameter. Without credentials, the
tool returns payment requirements so the agent knows what to pay.

Each tool registers itself in the discovery catalog (src/mcp/registry.py)
so agents can query /api/v1/docs/tools to discover available tools,
their parameters, access tiers, and pricing before connecting via MCP.
"""
import json
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from src.mcp.registry import ToolEntry, ToolParam, clear_tools, register_tool
from src.services.easter_egg import get_easter_egg
from src.services.items import create_item, get_item, list_items
from src.shared.auth.middleware import has_valid_api_key


def _auth_error() -> str:
    """Return a standard auth error response."""
    return json.dumps({
        "error": True,
        "code": "AUTH_REQUIRED",
        "message": "This tool requires authentication. Pass a valid API key in the 'api_key' parameter.",
    })


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
    async def items_create(name: str, description: str = "", api_key: str = "") -> str:
        """Create a new item. Requires API key in the api_key parameter."""
        if not has_valid_api_key(api_key):
            return _auth_error()
        item = create_item(name, description)
        return json.dumps(item)

    register_tool(ToolEntry(
        name="items_create",
        description="Create a new item. Requires API key.",
        access="auth",
        parameters=[
            ToolParam(name="name", type="string", required=True, description="Item name"),
            ToolParam(name="description", type="string", required=False, description="Item description"),
            ToolParam(name="api_key", type="string", required=True, description="Valid API key"),
        ],
    ))

    @server.tool()
    async def items_list(api_key: str = "") -> str:
        """List all items. Requires API key in the api_key parameter."""
        if not has_valid_api_key(api_key):
            return _auth_error()
        return json.dumps(list_items())

    register_tool(ToolEntry(
        name="items_list",
        description="List all items. Requires API key.",
        access="auth",
        parameters=[
            ToolParam(name="api_key", type="string", required=True, description="Valid API key"),
        ],
    ))

    @server.tool()
    async def items_get(item_id: str, api_key: str = "") -> str:
        """Get an item by ID. Requires API key in the api_key parameter."""
        if not has_valid_api_key(api_key):
            return _auth_error()
        item = get_item(item_id)
        if not item:
            return json.dumps({"error": True, "code": "NOT_FOUND", "message": f"Item {item_id} not found"})
        return json.dumps(item)

    register_tool(ToolEntry(
        name="items_get",
        description="Get an item by ID. Requires API key.",
        access="auth",
        parameters=[
            ToolParam(name="item_id", type="string", required=True, description="UUID of the item"),
            ToolParam(name="api_key", type="string", required=True, description="Valid API key"),
        ],
    ))

    # -- x402-gated tools --

    @server.tool()
    async def easter_egg(payment: str = "") -> str:
        """Get the easter egg message. Costs $0.05 USDC on Base.

        Call with no parameters to get payment requirements.
        Sign the payment using the x402 client SDK, then call again
        with the base64-encoded payment signature.
        """
        if payment:
            from src.shared.x402.server import verify_and_settle_payment
            settlement = await verify_and_settle_payment(payment)
            if settlement.get("error"):
                return json.dumps(settlement)
            result = get_easter_egg()
            result["settlement"] = settlement
            return json.dumps(result)

        from src.shared.x402.server import build_easter_egg_requirements
        return json.dumps(build_easter_egg_requirements())

    register_tool(ToolEntry(
        name="easter_egg",
        description="Get the easter egg message. Costs $0.05 USDC on Base.",
        access="x402",
        price="$0.05 USDC",
        network="base",
        parameters=[
            ToolParam(
                name="payment", type="string", required=False,
                description="Base64-encoded x402 payment signature. Call with no parameters first to get payment requirements.",
            ),
        ],
    ))

    # -- Auth-gated DB tools (require --profile full) --

    def _db_error() -> str:
        return json.dumps({
            "error": True,
            "code": "DB_UNAVAILABLE",
            "message": "Database not available. The service must be running with --profile full.",
        })

    @server.tool()
    async def notes_create(title: str, content: str = "", api_key: str = "") -> str:
        """Create a note (PostgreSQL-backed). Requires API key and --profile full."""
        if not has_valid_api_key(api_key):
            return _auth_error()
        try:
            from src.services.notes import create_note
            return json.dumps(create_note(title, content))
        except Exception:
            return _db_error()

    register_tool(ToolEntry(
        name="notes_create",
        description="Create a note (PostgreSQL-backed). Requires API key and --profile full.",
        access="auth",
        parameters=[
            ToolParam(name="title", type="string", required=True, description="Note title"),
            ToolParam(name="content", type="string", required=False, description="Note content"),
            ToolParam(name="api_key", type="string", required=True, description="Valid API key"),
        ],
    ))

    @server.tool()
    async def notes_list(api_key: str = "") -> str:
        """List all notes (PostgreSQL-backed). Requires API key and --profile full."""
        if not has_valid_api_key(api_key):
            return _auth_error()
        try:
            from src.services.notes import list_notes
            return json.dumps(list_notes())
        except Exception:
            return _db_error()

    register_tool(ToolEntry(
        name="notes_list",
        description="List all notes (PostgreSQL-backed). Requires API key and --profile full.",
        access="auth",
        parameters=[
            ToolParam(name="api_key", type="string", required=True, description="Valid API key"),
        ],
    ))

    @server.tool()
    async def notes_get(note_id: str, api_key: str = "") -> str:
        """Get a note by ID (PostgreSQL-backed). Requires API key and --profile full."""
        if not has_valid_api_key(api_key):
            return _auth_error()
        try:
            from src.services.notes import get_note
            note = get_note(note_id)
            if not note:
                return json.dumps({"error": True, "code": "NOT_FOUND", "message": f"Note {note_id} not found"})
            return json.dumps(note)
        except Exception:
            return _db_error()

    register_tool(ToolEntry(
        name="notes_get",
        description="Get a note by ID (PostgreSQL-backed). Requires API key and --profile full.",
        access="auth",
        parameters=[
            ToolParam(name="note_id", type="string", required=True, description="UUID of the note"),
            ToolParam(name="api_key", type="string", required=True, description="Valid API key"),
        ],
    ))
