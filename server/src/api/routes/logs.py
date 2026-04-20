"""Log query routes — auth-gated. Reads from local SQLite via trade_log."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends

from src.models.domain import Evaluation, Trade
from src.services import trade_log
from src.shared.auth.dependency import require_api_key

router = APIRouter(
    dependencies=[Depends(require_api_key)],
    tags=["logs"],
)


@router.get(
    "/strategies/{strategy_id}/evaluations",
    response_model=list[Evaluation],
    summary="Evaluation log for a strategy (newest first)",
)
async def list_evaluations(strategy_id: str, limit: int = 50, offset: int = 0) -> list[Evaluation]:
    return trade_log.list_evaluations(strategy_id, limit=limit, offset=offset)


@router.get(
    "/strategies/{strategy_id}/trades",
    response_model=list[Trade],
    summary="Trades for a strategy (newest first)",
)
async def list_trades_for_strategy(
    strategy_id: str, limit: int = 50, offset: int = 0,
) -> list[Trade]:
    return trade_log.list_trades(strategy_id, limit=limit, offset=offset)


@router.get(
    "/trades",
    response_model=list[Trade],
    summary="All trades across strategies (optional filters)",
)
async def list_all_trades(
    limit: int = 50,
    strategy_id: str | None = None,
    mode: Literal["live", "paper"] | None = None,
) -> list[Trade]:
    return trade_log.list_all_trades(limit=limit, strategy_id=strategy_id, mode=mode)
