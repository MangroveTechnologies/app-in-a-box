"""REST API routers.

/api/v1/*       -- Free and auth-gated endpoints
/api/v1/agent/* -- defi-agent endpoints (free discovery + auth-gated actions)
/api/x402/*     -- x402 payment-gated endpoints
"""
from fastapi import APIRouter

from src.api.routes.discovery import router as discovery_router
from src.api.routes.hello_mangrove import router as hello_mangrove_router

# Free + auth-gated
api_router = APIRouter(prefix="/api/v1")

# defi-agent namespace
agent_router = APIRouter(prefix="/agent")
agent_router.include_router(discovery_router, tags=["discovery"])

api_router.include_router(agent_router)

# x402 payment-gated (hello_mangrove is the smoke test for the payment path)
x402_router = APIRouter(prefix="/api/x402")
x402_router.include_router(hello_mangrove_router, tags=["x402"])
