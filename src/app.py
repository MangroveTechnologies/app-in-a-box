"""FastAPI application factory.

Serves dual protocols on a single port:
- REST API at /api/v1/* with OpenAPI 3.0 docs at /docs and /openapi.json
- MCP server at /mcp (Streamable HTTP transport)

x402 payment middleware (official Coinbase SDK) protects /api/v1/easter-egg.
All config loaded from per-environment JSON via app_config singleton.

Auto-documentation:
- Swagger UI: /docs (for humans)
- OpenAPI spec: /openapi.json (for agents)
- MCP tool catalog: /api/v1/docs/tools (for agents)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from src.config import app_config
from src.health import health_payload
from src.api.router import api_router
from src.shared.x402.config import (
    get_facilitator_url, get_network, get_pay_to,
    get_cdp_api_key_id, get_cdp_api_key_secret,
)

# x402 payment middleware (official SDK)
from x402.http.middleware.fastapi import payment_middleware
from x402.http import HTTPFacilitatorClient
from x402.http.facilitator_client_base import FacilitatorConfig, CreateHeadersAuthProvider
from x402 import x402ResourceServer
from x402.mechanisms.evm.exact import register_exact_evm_server
from x402.mechanisms.evm.exact.server import ExactEvmScheme


def _build_cdp_auth_provider():
    """Build auth provider for CDP facilitator if API keys are configured."""
    key_id = get_cdp_api_key_id()
    key_secret = get_cdp_api_key_secret()
    if not key_id or not key_secret:
        return None

    from urllib.parse import urlparse
    from cdp.auth import get_auth_headers, GetAuthHeadersOptions

    parsed = urlparse(get_facilitator_url())

    def create_headers():
        headers_map = {}
        for endpoint, method in [("verify", "POST"), ("settle", "POST"), ("supported", "GET")]:
            path = f"{parsed.path}/{endpoint}"
            h = get_auth_headers(GetAuthHeadersOptions(
                api_key_id=key_id,
                api_key_secret=key_secret,
                request_method=method,
                request_host=parsed.hostname,
                request_path=path,
            ))
            headers_map[endpoint] = h
        headers_map["list"] = headers_map.pop("supported")
        return headers_map

    return CreateHeadersAuthProvider(create_headers)


def _setup_x402():
    """Set up x402 payment middleware from app_config values."""
    facilitator_url = get_facilitator_url()
    network = get_network()
    pay_to = get_pay_to()

    auth_provider = _build_cdp_auth_provider()
    fc_config = FacilitatorConfig(url=facilitator_url)
    if auth_provider:
        fc_config = FacilitatorConfig(url=facilitator_url, auth_provider=auth_provider)

    facilitator = HTTPFacilitatorClient(config=fc_config)
    server = x402ResourceServer(facilitator)
    register_exact_evm_server(server)
    # Register V1 network names for CDP facilitator compatibility
    v1_scheme = ExactEvmScheme()
    server.register("base", v1_scheme)
    server.register("base-sepolia", v1_scheme)

    routes = {
        "GET /api/v1/easter-egg": {
            "accepts": {
                "scheme": "exact",
                "network": network,
                "payTo": pay_to,
                "price": "$0.05",
            },
            "resource": "Easter egg",
            "description": "Thank you for supporting the project and strengthening the ecosystem",
        },
    }

    return payment_middleware(routes, server)


x402_handler = _setup_x402()


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Mount MCP server
    from src.mcp.server import create_mcp_server
    mcp_server = create_mcp_server()
    application.mount("/mcp", mcp_server.streamable_http_app())
    yield


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

    API key holders bypass payment. This middleware only intercepts
    requests without an API key.
    """
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
