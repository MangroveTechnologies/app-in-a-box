"""backtest_service — quick + full backtest orchestration + IRR ranking.

Phase 3 Task 3.2. Thin orchestrator over mangroveai.backtesting.run().
The SDK exposes a single run() today; Tim is adding a dedicated quick
mode on the server. Until that ships, "quick" and "full" here both hit
run() — the distinction is in how we summarize results (quick = metrics
only; full = metrics + trade_history).

Filter + rank:
- Drop candidates with win_rate <= BACKTEST_MIN_WIN_RATE  (default 0.51)
- Drop candidates with total_trades < BACKTEST_MIN_TRADES (default 10)
- Sort survivors by irr_annualized DESC

Metric key lookup is defensive: the SDK's metrics dict field names may
vary. We look up several common spellings and return 0.0 if none present.
"""
from __future__ import annotations

import json
from typing import Any

from mangroveai.models import BacktestRequest
from pydantic import BaseModel

from src.config import app_config
from src.services.candidate_generator import StrategyCandidate
from src.shared.clients.mangrove import mangroveai_client
from src.shared.errors import SdkError
from src.shared.logging import get_logger

_log = get_logger(__name__)


# Reasonable defaults for an autonomous backtest. These match the defaults
# the strategy spec uses; advanced users can override via the manual path.
_DEFAULT_EXECUTION_CONFIG = {
    "initial_balance": 10_000.0,
    "min_balance_threshold": 0.1,
    "min_trade_amount": 25.0,
    "max_open_positions": 3,
    "max_trades_per_day": 10,
    "max_risk_per_trade": 0.02,
    "max_units_per_trade": 1_000_000.0,
    "max_trade_amount": 10_000_000.0,
    "volatility_window": 24,
    "target_volatility": 0.1,
}


class CandidateBacktestResult(BaseModel):
    """Per-candidate outcome of quick_backtest_all."""

    candidate: StrategyCandidate
    success: bool
    irr_annualized: float
    win_rate: float
    total_trades: int
    sharpe_ratio: float
    max_drawdown: float
    net_pnl: float
    reject_reason: str | None = None  # filled after filter step
    raw_metrics: dict[str, Any] = {}
    error: str | None = None


def _metric(metrics: dict[str, Any] | None, *keys: str, default: float = 0.0) -> float:
    """Defensive metric lookup: try each key in order."""
    if not metrics:
        return default
    for k in keys:
        if k in metrics and metrics[k] is not None:
            try:
                return float(metrics[k])
            except (TypeError, ValueError):
                continue
    return default


def _int_metric(metrics: dict[str, Any] | None, *keys: str, default: int = 0) -> int:
    if not metrics:
        return default
    for k in keys:
        if k in metrics and metrics[k] is not None:
            try:
                return int(metrics[k])
            except (TypeError, ValueError):
                continue
    return default


def _build_request(
    candidate: StrategyCandidate,
    lookback_months: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> BacktestRequest:
    """Build a BacktestRequest from a candidate + sensible defaults."""
    strategy_json = json.dumps({
        "name": candidate.name,
        "asset": candidate.asset,
        "entry": candidate.entry,
        "exit": candidate.exit or [],
    })
    return BacktestRequest(
        asset=candidate.asset,
        interval=candidate.timeframe,
        strategy_json=strategy_json,
        **_DEFAULT_EXECUTION_CONFIG,
        lookback_months=lookback_months if not start_date else None,
        start_date=start_date,
        end_date=end_date,
    )


def _summarize(
    candidate: StrategyCandidate,
    raw_result: Any,
) -> CandidateBacktestResult:
    """Translate an SDK BacktestResult into CandidateBacktestResult."""
    metrics: dict[str, Any] = getattr(raw_result, "metrics", None) or {}
    success = bool(getattr(raw_result, "success", False))
    return CandidateBacktestResult(
        candidate=candidate,
        success=success,
        irr_annualized=_metric(metrics, "irr_annualized", "irr", "annualized_return"),
        win_rate=_metric(metrics, "win_rate", "winrate"),
        total_trades=_int_metric(
            metrics,
            "total_trades",
            "trade_count",
            default=int(getattr(raw_result, "trade_count", None) or 0),
        ),
        sharpe_ratio=_metric(metrics, "sharpe_ratio", "sharpe"),
        max_drawdown=_metric(metrics, "max_drawdown", "maxdd"),
        net_pnl=_metric(metrics, "net_pnl", "total_pnl", "return"),
        raw_metrics=metrics,
        error=getattr(raw_result, "error", None),
    )


def quick_backtest_all(
    candidates: list[StrategyCandidate],
    lookback_months: int | None = None,
) -> list[CandidateBacktestResult]:
    """Run a backtest for every candidate. Per-candidate failures do not
    abort the batch — the result's .success and .error fields carry the
    outcome."""
    if lookback_months is None:
        lookback_months = int(app_config.BACKTEST_DEFAULT_LOOKBACK_MONTHS)

    client = mangroveai_client()
    results: list[CandidateBacktestResult] = []
    for c in candidates:
        try:
            raw = client.backtesting.run(
                _build_request(c, lookback_months=lookback_months),
            )
            results.append(_summarize(c, raw))
        except Exception as e:  # noqa: BLE001 — SDK may raise arbitrary subclasses
            results.append(CandidateBacktestResult(
                candidate=c,
                success=False,
                irr_annualized=0.0,
                win_rate=0.0,
                total_trades=0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                net_pnl=0.0,
                error=str(e),
            ))

    _log.info(
        "backtest.quick_batch_completed",
        n=len(candidates),
        succeeded=sum(1 for r in results if r.success),
    )
    return results


def filter_and_rank(
    results: list[CandidateBacktestResult],
    min_win_rate: float | None = None,
    min_trades: int | None = None,
) -> tuple[list[CandidateBacktestResult], list[CandidateBacktestResult]]:
    """Split results into (survivors, rejected), with rejected carrying a
    reject_reason. Survivors are sorted by irr_annualized DESC."""
    if min_win_rate is None:
        min_win_rate = float(app_config.BACKTEST_MIN_WIN_RATE)
    if min_trades is None:
        min_trades = int(app_config.BACKTEST_MIN_TRADES)

    survivors: list[CandidateBacktestResult] = []
    rejected: list[CandidateBacktestResult] = []

    for r in results:
        if not r.success:
            rejected.append(r.model_copy(update={"reject_reason": f"backtest failed: {r.error or 'unknown error'}"}))
            continue
        if r.total_trades < min_trades:
            rejected.append(r.model_copy(update={
                "reject_reason": f"total_trades {r.total_trades} < {min_trades}"
            }))
            continue
        if r.win_rate <= min_win_rate:
            rejected.append(r.model_copy(update={
                "reject_reason": f"win_rate {r.win_rate:.3f} <= {min_win_rate}"
            }))
            continue
        survivors.append(r)

    survivors.sort(key=lambda r: r.irr_annualized, reverse=True)
    return survivors, rejected


def full_backtest(
    candidate: StrategyCandidate,
    lookback_months: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> CandidateBacktestResult:
    """Run a full backtest — same SDK call as quick, but we also return
    the trade_history attached to raw_metrics for downstream display."""
    if lookback_months is None:
        lookback_months = int(app_config.BACKTEST_DEFAULT_LOOKBACK_MONTHS)

    client = mangroveai_client()
    try:
        raw = client.backtesting.run(
            _build_request(candidate, lookback_months, start_date, end_date),
        )
    except Exception as e:  # noqa: BLE001
        raise SdkError(
            f"Full backtest failed: {e}",
            suggestion="Check the strategy JSON is well-formed and the asset/interval are supported by mangroveai.",
        ) from e

    summary = _summarize(candidate, raw)
    # Attach trade history (if present) so the /strategies/autonomous response
    # can include it in full_backtest_metrics.
    trade_history = getattr(raw, "trade_history", None)
    if trade_history is not None:
        summary.raw_metrics = {**summary.raw_metrics, "trade_history": trade_history}

    _log.info(
        "backtest.full_completed",
        candidate_name=candidate.name,
        irr=summary.irr_annualized,
        win_rate=summary.win_rate,
        total_trades=summary.total_trades,
    )
    return summary
