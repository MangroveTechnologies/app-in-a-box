"""Strategy routes — auth-gated. All thin wrappers over strategy_service."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.services import backtest_service, strategy_service
from src.services.strategy_service import (
    StrategyAutonomousRequest,
    StrategyDetailResponse,
    StrategyManualRequest,
    StrategyStatusUpdate,
)
from src.shared.auth.dependency import require_api_key

router = APIRouter(
    prefix="/strategies",
    dependencies=[Depends(require_api_key)],
    tags=["strategies"],
)


class AutonomousResponse(BaseModel):
    strategy: StrategyDetailResponse
    generation_report: dict[str, Any]


@router.post(
    "/autonomous",
    response_model=AutonomousResponse,
    status_code=201,
    summary="Autonomous strategy creation from a natural-language goal",
)
async def create_autonomous(req: StrategyAutonomousRequest) -> AutonomousResponse:
    detail, report = strategy_service.create_autonomous(req)
    return AutonomousResponse(strategy=detail, generation_report=report)


@router.post(
    "/manual",
    response_model=StrategyDetailResponse,
    status_code=201,
    summary="Manual strategy creation with explicit entry/exit rules",
)
async def create_manual(req: StrategyManualRequest) -> StrategyDetailResponse:
    return strategy_service.create_manual(req)


@router.get(
    "",
    response_model=list[StrategyDetailResponse],
    summary="List strategies",
)
async def list_strategies(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[StrategyDetailResponse]:
    return strategy_service.list_strategies(status=status, limit=limit, offset=offset)


@router.get(
    "/{strategy_id}",
    response_model=StrategyDetailResponse,
    summary="Get a strategy by ID",
)
async def get_strategy(strategy_id: str) -> StrategyDetailResponse:
    return strategy_service.get_strategy(strategy_id)


@router.patch(
    "/{strategy_id}/status",
    response_model=StrategyDetailResponse,
    summary="Update strategy status (single source of truth for lifecycle)",
    description=(
        "Transitions: draft→inactive, inactive→{paper,live,archived}, "
        "paper→{live,inactive,archived}, live→{inactive,archived}. "
        "Target=live requires confirm=true AND an allocation block. "
        "Transition off live requires confirm=true."
    ),
)
async def update_status(strategy_id: str, req: StrategyStatusUpdate) -> StrategyDetailResponse:
    return strategy_service.update_status(strategy_id, req)


class BacktestInput(BaseModel):
    mode: str = "full"  # quick | full
    lookback_months: int = 3
    start_date: str | None = None
    end_date: str | None = None


@router.post(
    "/{strategy_id}/backtest",
    summary="Run a backtest on an existing strategy",
)
async def backtest(strategy_id: str, req: BacktestInput) -> dict:
    detail = strategy_service.get_strategy(strategy_id)
    # Build a StrategyCandidate shape from the stored strategy.
    from src.services.candidate_generator import StrategyCandidate
    candidate = StrategyCandidate(
        name=detail.name,
        asset=detail.asset,
        timeframe=detail.timeframe,
        entry=detail.entry,
        exit=detail.exit,
    )
    if req.mode == "quick":
        results = backtest_service.quick_backtest_all(
            [candidate], lookback_months=req.lookback_months,
        )
        result = results[0]
    else:
        result = backtest_service.full_backtest(
            candidate,
            lookback_months=req.lookback_months,
            start_date=req.start_date,
            end_date=req.end_date,
        )

    return {
        "strategy_id": strategy_id,
        "mode": req.mode,
        "metrics": {
            "irr_annualized": result.irr_annualized,
            "win_rate": result.win_rate,
            "total_trades": result.total_trades,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown": result.max_drawdown,
            "net_pnl": result.net_pnl,
        },
        "trade_history": result.raw_metrics.get("trade_history") if req.mode == "full" else None,
        "success": result.success,
        "error": result.error,
    }


@router.post(
    "/{strategy_id}/evaluate",
    summary="Manually trigger a single evaluation tick",
    description="Same code path the cron job runs. Useful for debugging or power-user workflows.",
)
async def evaluate(strategy_id: str) -> dict:
    # Make sure the strategy exists; strategy_service.get_strategy raises
    # StrategyNotFound otherwise.
    strategy_service.get_strategy(strategy_id)
    strategy_service.tick(strategy_id)
    # Return the latest evaluation row for this strategy.
    from src.services.trade_log import list_evaluations
    evs = list_evaluations(strategy_id, limit=1)
    if not evs:
        return {"strategy_id": strategy_id, "status": "no_evaluation_recorded"}
    e = evs[0]
    return {
        "strategy_id": strategy_id,
        "evaluation_id": e.id,
        "status": e.status,
        "order_count": len(e.order_intents),
        "duration_ms": e.duration_ms,
        "error_msg": e.error_msg,
    }
