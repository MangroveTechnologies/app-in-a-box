"""Discovery endpoints — free, no auth.

- GET /api/v1/agent/status: version, wallet count, strategies grouped
  by status, active cron jobs, db path, uptime.
- GET /api/v1/agent/tools: MCP tool catalog (auto-populated by
  src/mcp/tools.py at registration time).

/health lives in src/app.py (template-provided).
"""
from __future__ import annotations

import time
from collections import Counter

from fastapi import APIRouter

from src.config import app_config
from src.mcp.registry import list_tools as list_registered_tools
from src.services.scheduler_service import active_job_count
from src.shared.db.sqlite import get_connection

router = APIRouter()

_STARTUP_MONOTONIC = time.monotonic()


@router.get(
    "/status",
    summary="Agent status",
    description="Version, wallet count, strategies by status, active cron jobs, db path, uptime. Free, no auth.",
    tags=["discovery"],
)
async def status() -> dict:
    conn = get_connection()
    wallets_count = conn.execute("SELECT COUNT(*) AS c FROM wallets").fetchone()["c"]
    # Exclude the 'user-initiated' placeholder (plumbing for /dex/swap FK).
    strategy_rows = conn.execute(
        "SELECT status FROM strategies WHERE id != 'user-initiated'",
    ).fetchall()
    counts = Counter(r["status"] for r in strategy_rows)
    return {
        "version": "0.1.0",
        "wallets_count": wallets_count,
        "strategies": {
            "draft": counts.get("draft", 0),
            "inactive": counts.get("inactive", 0),
            "paper": counts.get("paper", 0),
            "live": counts.get("live", 0),
            "archived": counts.get("archived", 0),
        },
        "active_cron_jobs": active_job_count(),
        "db_path": str(app_config.DB_PATH),
        "uptime_seconds": int(time.monotonic() - _STARTUP_MONOTONIC),
    }


@router.get(
    "/tools",
    summary="MCP tool catalog",
    description="Full catalog of registered MCP tools: name, description, parameters, access tier, pricing. Free, no auth.",
    tags=["discovery"],
)
async def tools() -> dict:
    return {"tools": list_registered_tools()}
