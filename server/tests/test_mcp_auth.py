"""MCP tool auth and x402 payment enforcement tests.

Verifies the x402-gated hello_mangrove tool:
- Returns payment requirements when called without credentials
- Rejects malformed payment strings

Phase 4 will add auth tests for the defi-agent tools once they exist.
"""
import json
import os

os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402

from src.mcp.server import create_mcp_server  # noqa: E402


async def _call_tool(server, tool_name: str, args: dict | None = None) -> dict | list:
    """Call a named tool on the MCP server and return parsed JSON."""
    tools = server._tool_manager._tools
    tool = tools[tool_name]
    result = await tool.run(args or {})
    return json.loads(result)


@pytest.mark.asyncio
async def test_hello_mangrove_returns_payment_requirements_without_credentials():
    server = create_mcp_server()
    result = await _call_tool(server, "hello_mangrove")
    assert result["error"] is True
    assert result["code"] == "PAYMENT_REQUIRED"
    assert "payment_required" in result
    assert "payment_required_decoded" in result
    decoded = result["payment_required_decoded"]
    assert "accepts" in decoded
    assert len(decoded["accepts"]) > 0


@pytest.mark.asyncio
async def test_hello_mangrove_rejects_garbage_payment():
    server = create_mcp_server()
    result = await _call_tool(server, "hello_mangrove", {"payment": "not-valid-base64!!!"})
    assert result["error"] is True
    assert result["code"] == "INVALID_PAYMENT"
