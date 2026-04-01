"""Auto-documentation endpoints -- free, no auth required.

Provides programmatic discovery for both humans and agents:
- /api/v1/docs/tools: MCP tool catalog with access tiers, parameters, and pricing
- /docs: Swagger UI (provided by FastAPI, not defined here)
- /openapi.json: OpenAPI 3.0 spec (provided by FastAPI, not defined here)
"""
from fastapi import APIRouter

from src.mcp.registry import list_tools

router = APIRouter()


@router.get(
    "/docs/tools",
    summary="MCP tool catalog",
    description="Lists all registered MCP tools with their access tier, parameters, "
    "and pricing. Agents should call this before connecting via MCP to discover "
    "what tools are available and what each one costs.",
    response_description="List of MCP tools with metadata",
)
async def tool_catalog():
    """Return the full MCP tool catalog for agent discovery.

    Each tool entry includes:
    - name: Tool identifier used in MCP calls
    - description: What the tool does
    - access: "free", "auth" (API key required), or "x402" (payment required)
    - parameters: List of input parameters with types
    - price: Cost per call (x402 tools only)
    - network: Blockchain network (x402 tools only)
    """
    tools = list_tools()
    return {
        "tools": tools,
        "total": len(tools),
        "access_tiers": {
            "free": "No credentials required",
            "auth": "Requires X-API-Key header",
            "x402": "Requires x402 payment (or API key for free access)",
        },
    }
