"""Reference strategies routes — auth-gated.

Exposes the curated seed set as a public API surface. When MangroveAI
ships a public reference-strategies endpoint (issue #156 trickle-down),
these routes continue to work and the backing service swaps its source.

- GET  /api/v1/agent/reference-strategies/search
- GET  /api/v1/agent/reference-strategies/{reference_id}
- POST /api/v1/agent/reference-strategies/{reference_id}/build
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.services import reference_strategies_service
from src.shared.auth.dependency import require_api_key

router = APIRouter(
    prefix="/reference-strategies",
    dependencies=[Depends(require_api_key)],
    tags=["reference-strategies"],
)


class ReferenceSearchResponse(BaseModel):
    asset: str
    timeframe: str | None
    category: str | None
    count: int
    strategies: list[dict[str, Any]]


@router.get(
    "/search",
    response_model=ReferenceSearchResponse,
    summary="Search curated reference strategies",
    description=(
        "Returns up to `limit` reference strategies matching the filter. "
        "Ranks by match specificity: asset+timeframe+category > "
        "asset+timeframe > asset > category. When `category` is omitted "
        "and `goal_hint` is supplied, a category is auto-detected. "
        "Mechanism 2 of the /create-strategy skill — the agent picks from "
        "these instead of library-default parameter guessing."
    ),
)
async def search_references(
    asset: str,
    timeframe: str | None = None,
    category: str | None = None,
    goal_hint: str | None = None,
    limit: int = 5,
) -> ReferenceSearchResponse:
    results = reference_strategies_service.search(
        asset=asset,
        timeframe=timeframe,
        category=category,
        goal_hint=goal_hint,
        limit=limit,
    )
    return ReferenceSearchResponse(
        asset=asset.upper(),
        timeframe=timeframe,
        category=category,
        count=len(results),
        strategies=[r.model_dump() for r in results],
    )


@router.get(
    "/{reference_id}",
    summary="Get a single reference strategy by id",
)
async def get_reference(reference_id: str) -> dict[str, Any]:
    ref = reference_strategies_service.get(reference_id)
    if ref is None:
        raise HTTPException(status_code=404, detail=f"reference_id {reference_id!r} not found")
    return ref.model_dump()


class BuildFromReferenceRequest(BaseModel):
    timeframe: str | None = None  # Defaults to the reference's own timeframe.
    asset: str | None = None  # Retarget onto a different asset; defaults to the reference's own.
    name: str | None = None  # Optional override; auto-labelled if omitted.


@router.post(
    "/{reference_id}/build",
    summary="Materialize a create-strategy-manual payload from a reference",
    description=(
        "Copies the reference's signals exactly. `timeframe` and `asset` "
        "are free-to-override — a reference strategy is a portable signal "
        "combo, not a pin to the source asset/timeframe. Returns a payload "
        "the caller can POST to /strategies/manual as-is, or bulk-backtest "
        "by calling build N times across candidate references and routing "
        "each result through /backtest."
    ),
)
async def build_from_reference(
    reference_id: str,
    req: BuildFromReferenceRequest,
) -> dict[str, Any]:
    try:
        return reference_strategies_service.build_from_reference(
            reference_id=reference_id,
            timeframe_override=req.timeframe,
            asset_override=req.asset,
            name=req.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
