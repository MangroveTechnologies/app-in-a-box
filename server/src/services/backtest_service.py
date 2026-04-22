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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mangroveai.models import BacktestRequest
from pydantic import BaseModel

from src.config import app_config
from src.services.candidate_generator import StrategyCandidate
from src.shared import timeframes
from src.shared.clients.mangrove import mangroveai_client
from src.shared.errors import SdkError
from src.shared.logging import get_logger

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Canonical trading defaults — copied verbatim from MangroveAI.
#
# Source: MangroveAI/domains/ai_copilot/prompts/trading_defaults.json
# Loaded the way MangroveAI/domains/strategies/services.py does:
# flatten risk_management + position_limits + volatility_settings +
# trading_rules + time_based_exits into a single dict.
#
# The SDK's BacktestRequest declares 13 fields as required (pydantic
# PydanticUndefined default) despite the server applying trading_defaults
# fallback on its own. Until MangroveAI issue #437 lands (make those 10
# duplicate-forcing fields Optional), every client has to supply the
# values. We read from our copy of the upstream JSON so the values stay
# in sync — `git diff server/src/services/data/trading_defaults.json`
# against the upstream file is the drift check.
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent / "data"
_TRADING_DEFAULTS_PATH = _DATA_DIR / "trading_defaults.json"

with _TRADING_DEFAULTS_PATH.open() as _f:
    TRADING_DEFAULTS: dict[str, Any] = json.load(_f)


def flattened_defaults() -> dict[str, Any]:
    """Flatten the trading_defaults sections into a single dict.

    Mirrors MangroveAI/domains/strategies/services.py:306-309 — the same
    sections in the same order, so a config override that works against
    the upstream copilot works identically here.
    """
    out: dict[str, Any] = {}
    for section in (
        "risk_management",
        "position_limits",
        "volatility_settings",
        "trading_rules",
        "time_based_exits",
    ):
        section_data = TRADING_DEFAULTS.get(section) or {}
        out.update(section_data)
    return out


def backtest_cost_defaults() -> dict[str, Any]:
    """Return the slippage_pct / fee_pct defaults.

    These live under `backtest_defaults` in the upstream JSON (separate
    from the execution config sections) so they need a dedicated
    accessor when a caller wants to surface them.
    """
    return dict(TRADING_DEFAULTS.get("backtest_defaults") or {})


def _resolve_window(
    timeframe: str,
    lookback_months: int | None,
    lookback_days: int | None = None,
    lookback_hours: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[int | None, str | None, str | None]:
    """Resolve a lookback specification to (lookback_months, start_date, end_date).

    Precedence (most specific first):
      1. explicit start_date + end_date (pass-through)
      2. lookback_hours (converted to pinned ISO window ending now)
      3. lookback_days (same)
      4. lookback_months (pass-through — server converts using 30d/month)
      5. if none given, recommended by timeframe via
         `timeframes.recommended_lookback_months`

    Returns a tuple where the lookback_months entry is ``None`` whenever
    explicit dates are returned (matches BacktestRequest's "dates take
    precedence over lookback_months" contract).
    """
    # 1. pass-through for explicit dates
    if start_date and end_date:
        return None, start_date, end_date

    # 2/3. hours and days → compute ISO window ending now (UTC)
    if lookback_hours is not None and lookback_hours > 0:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=lookback_hours)
        return None, start.isoformat(), end.isoformat()
    if lookback_days is not None and lookback_days > 0:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)
        return None, start.isoformat(), end.isoformat()

    # 4. explicit months
    if lookback_months is not None and lookback_months > 0:
        return lookback_months, start_date, end_date

    # 5. auto by timeframe (matches MangroveAI prompt_builder.py defaults)
    return timeframes.recommended_lookback_months(timeframe), start_date, end_date


# `_DEFAULT_EXECUTION_CONFIG` removed — use `flattened_defaults()` + caller override.
# The old hardcoded dict had drifted from upstream trading_defaults.json
# (max_risk_per_trade 0.02 vs 0.01, max_open_positions 3 vs 10,
# max_trades_per_day 10 vs 50). Single source of truth now.


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
    lookback_months: int | None,
    start_date: str | None = None,
    end_date: str | None = None,
    config: dict[str, Any] | None = None,
) -> BacktestRequest:
    """Build a BacktestRequest from a candidate + canonical trading defaults.

    `config` is merged over `flattened_defaults()` — the single source of
    truth is `data/trading_defaults.json`. Any key a caller passes in
    `config` wins. Keys the SDK doesn't recognize are forwarded anyway
    (BacktestRequest has `model_config={'extra': 'allow'}`, verified
    2026-04-22) — the server treats them as execution_config extras.

    Slippage, fee, and max_hold_time_hours are just keys in `config`
    now. Callers no longer need dedicated arguments for them.
    """
    # Reject unsupported timeframes up front (1m etc.) — see
    # src.shared.timeframes.canonicalize_timeframe for the whitelist.
    interval = timeframes.canonicalize_timeframe(candidate.timeframe)

    merged = {**flattened_defaults(), **(config or {})}

    strategy_json = json.dumps({
        "name": candidate.name,
        "asset": candidate.asset,
        "entry": candidate.entry,
        "exit": candidate.exit or [],
    })
    kwargs: dict[str, Any] = {
        "asset": candidate.asset,
        "interval": interval,
        "strategy_json": strategy_json,
        **merged,
        "lookback_months": lookback_months if not start_date else None,
        "start_date": start_date,
        "end_date": end_date,
    }
    return BacktestRequest(**kwargs)


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
    outcome.

    If `lookback_months` is None, picks the timeframe-aware recommended
    default per `timeframes.recommended_lookback_months`. All candidates
    are assumed to share the same timeframe (they come from one
    candidate_generator.generate() call), so the first one drives the
    recommendation.
    """
    if lookback_months is None and candidates:
        lookback_months = timeframes.recommended_lookback_months(candidates[0].timeframe)
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
    lookback_days: int | None = None,
    lookback_hours: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    config: dict[str, Any] | None = None,
) -> CandidateBacktestResult:
    """Run a full backtest — same SDK call as quick, plus trade_history
    in raw_metrics for downstream display.

    Lookback resolution (first non-null wins):
      start_date+end_date > lookback_hours > lookback_days > lookback_months
      > timeframes.recommended_lookback_months(candidate.timeframe).

    `config` merges over the canonical `flattened_defaults()` from
    `data/trading_defaults.json`. Any key goes: the upstream execution
    knobs (initial_balance, max_risk_per_trade, atr_period, …), plus the
    three BacktestRequest-level optionals (slippage_pct, fee_pct,
    max_hold_time_hours), plus anything upstream adds later — the SDK
    model is `extra='allow'`, so unknown keys round-trip to the server
    without client-side error.
    """
    resolved_months, resolved_start, resolved_end = _resolve_window(
        candidate.timeframe,
        lookback_months,
        lookback_days=lookback_days,
        lookback_hours=lookback_hours,
        start_date=start_date,
        end_date=end_date,
    )

    client = mangroveai_client()
    try:
        raw = client.backtesting.run(
            _build_request(
                candidate,
                lookback_months=resolved_months,
                start_date=resolved_start,
                end_date=resolved_end,
                config=config,
            ),
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
    # Record the resolved window so downstream callers can surface it to
    # the user (and detect fallbacks from the server).
    summary.raw_metrics = {
        **summary.raw_metrics,
        "resolved_window": {
            "lookback_months": resolved_months,
            "start_date": resolved_start,
            "end_date": resolved_end,
            "requested_timeframe": candidate.timeframe,
        },
    }

    _log.info(
        "backtest.full_completed",
        candidate_name=candidate.name,
        irr=summary.irr_annualized,
        win_rate=summary.win_rate,
        total_trades=summary.total_trades,
        resolved_months=resolved_months,
        resolved_start=resolved_start,
        resolved_end=resolved_end,
    )
    return summary
