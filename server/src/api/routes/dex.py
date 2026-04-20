"""DEX routes — auth-gated.

- GET  /api/v1/agent/dex/venues
- GET  /api/v1/agent/dex/pairs?venue_id
- POST /api/v1/agent/dex/quote
- POST /api/v1/agent/dex/swap (requires confirm=true)

venues/pairs/quote pass through to mangrovemarkets.dex directly. swap
builds an OrderIntent and hands it to order_executor — the SINGLE swap
path used for both user-initiated and cron-driven trades.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.models.domain import OrderIntent
from src.services.order_executor import execute_one
from src.shared.auth.dependency import require_api_key
from src.shared.clients.mangrove import mangrovemarkets_client
from src.shared.errors import ConfirmationRequired, SdkError

router = APIRouter(
    prefix="/dex",
    dependencies=[Depends(require_api_key)],
    tags=["dex"],
)


@router.get("/venues", summary="List DEX venues")
async def dex_venues() -> list[Any]:
    try:
        venues = mangrovemarkets_client().dex.supported_venues()
    except Exception as e:  # noqa: BLE001
        raise SdkError(f"dex.supported_venues failed: {e}") from e
    return [v.model_dump() if hasattr(v, "model_dump") else v for v in venues]


@router.get("/pairs", summary="List trading pairs for a venue")
async def dex_pairs(venue_id: str) -> list[Any]:
    try:
        pairs = mangrovemarkets_client().dex.supported_pairs(venue_id=venue_id)
    except Exception as e:  # noqa: BLE001
        raise SdkError(f"dex.supported_pairs failed: {e}") from e
    return [p.model_dump() if hasattr(p, "model_dump") else p for p in pairs]


class QuoteRequest(BaseModel):
    input_token: str
    output_token: str
    amount: float
    chain_id: int
    venue_id: str | None = None


@router.post("/quote", summary="Get a swap quote")
async def dex_quote(req: QuoteRequest) -> dict:
    try:
        quote = mangrovemarkets_client().dex.get_quote(
            input_token=req.input_token,
            output_token=req.output_token,
            amount=req.amount,
            chain_id=req.chain_id,
            venue_id=req.venue_id,
        )
    except Exception as e:  # noqa: BLE001
        raise SdkError(f"dex.get_quote failed: {e}") from e
    return quote.model_dump() if hasattr(quote, "model_dump") else quote


class SwapRequest(BaseModel):
    input_token: str
    output_token: str
    amount: float
    chain_id: int
    wallet_address: str
    slippage: float = 1.0
    mev_protection: bool = False
    venue_id: str | None = None
    confirm: bool = Field(
        False,
        description="Must be true. Protects against agent-initiated swaps without user approval.",
    )


@router.post(
    "/swap",
    summary="Execute a DEX swap",
    description=(
        "Full 6-step flow: quote → conditional approve → sign → broadcast → poll → "
        "prepare → sign → broadcast → poll. Signing is client-side; SDK never sees keys. "
        "Requires confirm=true."
    ),
)
async def dex_swap(req: SwapRequest) -> dict:
    if not req.confirm:
        raise ConfirmationRequired(
            "DEX swaps require confirm=true.",
            suggestion="Re-submit with confirm=true. This is intentional — protects against agent-initiated swaps without user approval.",
        )

    # Build an OrderIntent from the user's request. side=buy means "spend
    # input_token to get output_token"; from the intent's perspective the
    # symbol is the non-USDC leg.
    if req.output_token.upper() == "USDC":
        side = "sell"
        symbol = req.input_token
    else:
        side = "buy"
        symbol = req.output_token

    intent = OrderIntent(
        action="enter",
        side=side,
        symbol=symbol,
        amount=req.amount,
        reason="user-initiated",
    )

    trade = execute_one(
        intent,
        mode="live",
        wallet_address=req.wallet_address,
        chain_id=req.chain_id,
        venue_id=req.venue_id,
    )
    return {
        "tx_hash": trade.tx_hash,
        "status": trade.status,
        "input_token": trade.input_token,
        "input_amount": trade.input_amount,
        "output_token": trade.output_token,
        "output_amount": trade.output_amount,
        "fill_price": trade.fill_price,
        "fees": trade.fees,
        "approval_tx_hash": trade.fees.get("approval_tx_hash"),
        "trade_log_id": trade.id,
    }
