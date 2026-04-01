"""Easter egg endpoint -- x402-gated ($0.05 USDC on Base).

API key holders get free access (bypasses x402 middleware in app.py).
Public agents pay via x402 protocol -- the middleware handles 402 response,
payment verification, and settlement automatically.

Demonstrates the x402-gated access tier.
"""
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from src.services.easter_egg import get_easter_egg

router = APIRouter()


class EasterEggResponse(BaseModel):
    """Easter egg message response."""
    message: str = Field(description="Thank-you message for supporters")
    timestamp: str = Field(description="Server timestamp (ISO 8601)")


@router.get(
    "/easter-egg",
    response_model=EasterEggResponse,
    summary="Easter egg (x402-gated)",
    description="Returns a thank-you message. Costs $0.05 USDC on Base for public agents. "
    "API key holders get free access. Returns 402 with payment requirements if no "
    "credentials are provided. Payment verification and settlement handled by "
    "the x402 middleware via Coinbase facilitator.",
    responses={
        200: {"description": "Easter egg message (authenticated or paid)"},
        402: {"description": "Payment required -- includes x402 payment options"},
    },
)
async def easter_egg(request: Request, x_api_key: str = Header(None, alias="X-API-Key")):
    # API key holders get free access (middleware already let them through)
    # This route only executes after either:
    # 1. API key bypassed middleware, or
    # 2. x402 middleware verified and will settle the payment
    return get_easter_egg()
