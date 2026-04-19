"""MCP tool definitions.

For now this only registers the `hello_mangrove` x402 demo tool — the smoke
test for the payment pipeline. The defi-agent tools (wallet, strategy, dex,
etc.) are registered in Phase 4 Task 4.7.

Both REST routes and MCP tools call the same service-layer functions,
never duplicating business logic.
"""
import json

from mcp.server.fastmcp import FastMCP

from src.mcp.registry import ToolEntry, ToolParam, clear_tools, register_tool
from src.services.hello_mangrove import get_hello_mangrove


def register(server: FastMCP):
    """Register all tools on the MCP server and discovery catalog."""
    # Clear catalog to avoid duplicates on re-registration
    clear_tools()

    # -- x402-gated demo tool --

    @server.tool()
    async def hello_mangrove(payment: str = "") -> str:
        """Get the hello_mangrove message. Costs $0.05 USDC on Base.

        Call with no parameters to get payment requirements.
        Sign the payment using the x402 client SDK, then call again
        with the base64-encoded payment signature.
        """
        if payment:
            from src.shared.x402.server import verify_and_settle_payment
            settlement = await verify_and_settle_payment(payment)
            if settlement.get("error"):
                return json.dumps(settlement)
            result = get_hello_mangrove()
            result["settlement"] = settlement
            return json.dumps(result)

        from src.shared.x402.server import build_hello_mangrove_requirements
        return json.dumps(build_hello_mangrove_requirements())

    register_tool(ToolEntry(
        name="hello_mangrove",
        description="Get the hello_mangrove message. Costs $0.05 USDC on Base. Smoke test for the x402 payment path.",
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
