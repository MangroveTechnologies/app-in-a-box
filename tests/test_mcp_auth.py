"""MCP tool auth and x402 payment enforcement tests.

Verifies that MCP tools actually enforce access control:
- Auth-gated tools reject calls without a valid API key
- x402-gated tools return payment requirements when called without credentials
- x402-gated tools grant access when called with a valid API key
"""
import json
import os

os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402

from src.mcp.server import create_mcp_server  # noqa: E402
from src.services.items import clear_items  # noqa: E402


async def _call_tool(server, tool_name: str, args: dict | None = None) -> dict | list:
    """Call a named tool on the MCP server and return parsed JSON."""
    tools = server._tool_manager._tools
    tool = tools[tool_name]
    result = await tool.run(args or {})
    return json.loads(result)


@pytest.fixture(autouse=True)
def _cleanup():
    clear_items()
    yield
    clear_items()


# -- Auth-gated tools --


@pytest.mark.asyncio
async def test_items_create_rejects_without_api_key():
    server = create_mcp_server()
    result = await _call_tool(server, "items_create", {"name": "test"})
    assert result["error"] is True
    assert result["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_items_create_rejects_invalid_api_key():
    server = create_mcp_server()
    result = await _call_tool(server, "items_create", {"name": "test", "api_key": "bad-key"})
    assert result["error"] is True
    assert result["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_items_create_accepts_valid_api_key():
    server = create_mcp_server()
    result = await _call_tool(server, "items_create", {"name": "test", "api_key": "test-key-1"})
    assert "error" not in result
    assert result["name"] == "test"
    assert "id" in result


@pytest.mark.asyncio
async def test_items_list_rejects_without_api_key():
    server = create_mcp_server()
    result = await _call_tool(server, "items_list")
    assert result["error"] is True
    assert result["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_items_list_accepts_valid_api_key():
    server = create_mcp_server()
    result = await _call_tool(server, "items_list", {"api_key": "test-key-1"})
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_items_get_rejects_without_api_key():
    server = create_mcp_server()
    result = await _call_tool(server, "items_get", {"item_id": "abc"})
    assert result["error"] is True
    assert result["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_items_get_accepts_valid_api_key():
    server = create_mcp_server()
    created = await _call_tool(server, "items_create", {"name": "lookup", "api_key": "test-key-1"})
    result = await _call_tool(server, "items_get", {"item_id": created["id"], "api_key": "test-key-1"})
    assert result["name"] == "lookup"


# -- x402-gated tools --


@pytest.mark.asyncio
async def test_easter_egg_returns_payment_requirements_without_credentials():
    server = create_mcp_server()
    result = await _call_tool(server, "easter_egg")
    assert result["error"] is True
    assert result["code"] == "PAYMENT_REQUIRED"
    assert "payment_required" in result
    assert "payment_required_decoded" in result
    decoded = result["payment_required_decoded"]
    assert "accepts" in decoded
    assert len(decoded["accepts"]) > 0


@pytest.mark.asyncio
async def test_easter_egg_rejects_garbage_payment():
    server = create_mcp_server()
    result = await _call_tool(server, "easter_egg", {"payment": "not-valid-base64!!!"})
    assert result["error"] is True
    assert result["code"] == "INVALID_PAYMENT"
