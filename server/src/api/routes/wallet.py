"""Wallet routes — auth-gated.

- POST /api/v1/agent/wallet/create: create + store an encrypted wallet
- GET  /api/v1/agent/wallet/list: list stored wallets (no secrets)
- GET  /api/v1/agent/wallet/{address}/balances: token balances via SDK
- GET  /api/v1/agent/wallet/{address}/portfolio: aggregate portfolio
- GET  /api/v1/agent/wallet/{address}/history: transaction history

wallet_manager handles create + list (local encryption). The three
read endpoints pass through to mangrovemarkets_client directly — no
wrapper service by design (see architecture doc).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.services.wallet_manager import (
    WalletCreateResponse,
    WalletListItem,
    create_wallet,
    list_wallets,
)
from src.shared.auth.dependency import require_api_key
from src.shared.clients.mangrove import mangrovemarkets_client
from src.shared.errors import SdkError

router = APIRouter(
    prefix="/wallet",
    dependencies=[Depends(require_api_key)],
    tags=["wallet"],
)


class WalletCreateRequest(BaseModel):
    chain: str = Field(..., description="evm | xrpl (xrpl stubbed 501 in v1)")
    network: str = Field("testnet", description="mainnet | testnet")
    chain_id: int | None = Field(None, description="Required for evm")
    label: str | None = None


@router.post(
    "/create",
    response_model=WalletCreateResponse,
    summary="Create a new wallet",
    description=(
        "Creates + encrypts a wallet locally. The seed phrase is returned "
        "ONCE here and never retrievable via the API afterwards. EVM only "
        "in v1; XRPL returns 501."
    ),
    status_code=201,
)
async def wallet_create(req: WalletCreateRequest) -> WalletCreateResponse:
    return create_wallet(
        chain=req.chain,
        network=req.network,
        chain_id=req.chain_id,
        label=req.label,
    )


@router.get(
    "/list",
    response_model=list[WalletListItem],
    summary="List stored wallets",
    description="Returns addresses + metadata only. Never includes secrets.",
)
async def wallet_list() -> list[WalletListItem]:
    return list_wallets()


@router.get(
    "/{address}/balances",
    summary="Token balances",
    description="Pass-through to mangrovemarkets.dex.balances(chain_id, wallet).",
)
async def wallet_balances(address: str, chain_id: int) -> Any:
    try:
        result = mangrovemarkets_client().dex.balances(chain_id=chain_id, wallet=address)
    except Exception as e:  # noqa: BLE001
        raise SdkError(f"dex.balances failed: {e}") from e
    return result.model_dump() if hasattr(result, "model_dump") else result


@router.get(
    "/{address}/portfolio",
    summary="Portfolio aggregate",
    description="Combined value + P&L + tokens + DeFi via mangrovemarkets.portfolio.*.",
)
async def wallet_portfolio(address: str, chain_id: int | None = None) -> dict:
    client = mangrovemarkets_client()
    try:
        value = client.portfolio.value(addresses=address, chain_id=chain_id)
        pnl = client.portfolio.pnl(addresses=address, chain_id=chain_id)
        tokens = client.portfolio.tokens(addresses=address, chain_id=chain_id)
        defi = client.portfolio.defi(addresses=address, chain_id=chain_id)
    except Exception as e:  # noqa: BLE001
        raise SdkError(f"portfolio query failed: {e}") from e
    return {
        "value": value.model_dump() if hasattr(value, "model_dump") else value,
        "pnl": pnl.model_dump() if hasattr(pnl, "model_dump") else pnl,
        "tokens": tokens.model_dump() if hasattr(tokens, "model_dump") else tokens,
        "defi": defi.model_dump() if hasattr(defi, "model_dump") else defi,
    }


@router.get(
    "/{address}/history",
    summary="Transaction history",
    description="Pass-through to mangrovemarkets.portfolio.history.",
)
async def wallet_history(address: str, limit: int = 50) -> list[Any]:
    try:
        items = mangrovemarkets_client().portfolio.history(address=address, limit=limit)
    except Exception as e:  # noqa: BLE001
        raise SdkError(f"portfolio.history failed: {e}") from e
    return [i.model_dump() if hasattr(i, "model_dump") else i for i in items]
