"""REST API routers.

/api/v1/*   -- Free and auth-gated endpoints
/api/x402/* -- x402 payment-gated endpoints
"""
from fastapi import APIRouter

from src.api.routes.hello_mangrove import router as hello_mangrove_router

# Free + auth-gated (placeholder for defi-agent routes added in Phase 4)
api_router = APIRouter(prefix="/api/v1")

# x402 payment-gated (hello_mangrove is the smoke test for the payment path)
x402_router = APIRouter(prefix="/api/x402")
x402_router.include_router(hello_mangrove_router, tags=["x402"])
