"""FastAPI application factory.

Serves dual protocols on a single port:
- REST API at /api/v1/* with OpenAPI 3.0 docs at /docs and /openapi.json
- MCP server at /mcp (Streamable HTTP transport)

x402 payment middleware (official Coinbase SDK) protects /api/v1/easter-egg.
Supports both CDP facilitator (mainnet) and x402.org (testnet) via env vars.

Auto-documentation:
- Swagger UI: /docs (for humans)
- OpenAPI spec: /openapi.json (for agents)
- MCP tool catalog: /api/v1/docs/tools (for agents)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from src.health import health_payload
from src.api.router import api_router
from src.shared.x402.config import FACILITATOR_URL, NETWORK, PAY_TO

# x402 payment middleware (official SDK)
from x402.http.middleware.fastapi import payment_middleware
from x402.http import HTTPFacilitatorClient
from x402 import x402ResourceServer
from x402.mechanisms.evm.exact import register_exact_evm_server


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Mount MCP server
    from src.mcp.server import create_mcp_server
    mcp_server = create_mcp_server()
    application.mount("/mcp", mcp_server.streamable_http_app())
    yield


# -- x402 payment middleware setup --
from x402.http.facilitator_client_base import FacilitatorConfig
facilitator = HTTPFacilitatorClient(config=FacilitatorConfig(url=FACILITATOR_URL))
x402_server = x402ResourceServer(facilitator)
register_exact_evm_server(x402_server)

x402_routes = {
    "GET /api/v1/easter-egg": {
        "accepts": {
            "scheme": "exact",
            "network": NETWORK,
            "payTo": PAY_TO,
            "price": "$0.05",
        },
        "resource": "Easter egg",
        "description": "Thank you for supporting the project and strengthening the ecosystem",
    },
}

x402_handler = payment_middleware(x402_routes, x402_server)


app = FastAPI(
    title="x402 App Template",
    description=(
        "FastAPI + MCP service template with three-tier access control.\n\n"
        "## For Agents\n\n"
        "- **REST discovery**: GET `/openapi.json` for the full OpenAPI 3.0 spec\n"
        "- **MCP tool catalog**: GET `/api/v1/docs/tools` for tool names, parameters, access tiers, and pricing\n"
        "- **MCP endpoint**: Connect to `/mcp` via Streamable HTTP transport\n\n"
        "## Access Tiers\n\n"
        "| Tier | How to access |\n"
        "|------|---------------|\n"
        "| Free | No credentials needed |\n"
        "| Auth | `X-API-Key` header |\n"
        "| x402 | Payment via x402 protocol (or API key for free access) |\n"
    ),
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "discovery", "description": "API and tool discovery endpoints (free, no auth)"},
        {"name": "echo", "description": "Echo/reflect endpoints (free, no auth)"},
        {"name": "items", "description": "Items CRUD (auth-gated, requires API key)"},
        {"name": "easter-egg", "description": "Easter egg endpoint (x402-gated, $0.05 USDC on Base)"},
    ],
)


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    """x402 payment middleware -- protects easter-egg endpoint.

    API key holders bypass payment via the route handler (not this middleware).
    This middleware only intercepts requests without an API key.
    """
    # Let API key holders through without payment
    api_key = request.headers.get("x-api-key")
    if api_key:
        return await call_next(request)
    return await x402_handler(request, call_next)


app.include_router(api_router)


@app.get(
    "/health",
    summary="Health check",
    description="Returns service health status and timestamp. Free, no auth required.",
    tags=["discovery"],
)
async def health():
    return health_payload()
