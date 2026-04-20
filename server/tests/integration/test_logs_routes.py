"""Integration tests for log query routes."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.models.domain import Evaluation, OrderIntent, Trade  # noqa: E402

_API_KEY = "test-key-1"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "logs.db"
    from src.config import app_config
    from src.services import scheduler_service as ss
    from src.shared.db import sqlite as db_mod

    monkeypatch.setattr(app_config, "DB_PATH", str(db_file))
    db_mod.reset_connection()
    ss.reset_scheduler_cache()

    from src.shared.db.sqlite import get_connection, init_db
    init_db()

    # Seed one strategy + a handful of evaluations + trades.
    conn = get_connection()
    conn.execute(
        """INSERT INTO strategies (id, mangrove_id, name, asset, timeframe, status,
           entry_json, exit_json, execution_config_json, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        ("s1", "mg-s1", "t", "ETH", "1h", "paper", "[]", "[]", "{}",
         "2026-04-20T00:00:00+00:00", "2026-04-20T00:00:00+00:00"),
    )
    conn.commit()

    from src.services.trade_log import log_evaluation, log_trade

    now = datetime.now(timezone.utc)
    for i in range(3):
        log_evaluation(Evaluation(
            id=str(uuid.uuid4()), strategy_id="s1",
            timestamp=now - timedelta(minutes=i),
            duration_ms=42, status="ok",
        ))
    for i, mode in enumerate(["paper", "live", "paper"]):
        log_trade(Trade(
            id=str(uuid.uuid4()), strategy_id="s1",
            order_intent=OrderIntent(action="enter", side="buy", symbol="ETH", amount=0.1),
            mode=mode,
            tx_hash="0x" + str(i) * 40 if mode == "live" else None,
            input_token="USDC", input_amount=100.0,
            output_token="ETH", output_amount=0.04,
            fill_price=2500.0, fees={},
            status="simulated" if mode == "paper" else "confirmed",
            executed_at=now - timedelta(minutes=i),
        ))

    from src.app import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c
    ss.reset_scheduler_cache()
    db_mod.reset_connection()


def _auth() -> dict:
    return {"X-API-Key": _API_KEY}


def test_list_evaluations(client):
    r = client.get("/api/v1/agent/strategies/s1/evaluations", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    # Newest first
    ts = [item["timestamp"] for item in body]
    assert ts == sorted(ts, reverse=True)


def test_list_trades_for_strategy(client):
    r = client.get("/api/v1/agent/strategies/s1/trades", headers=_auth())
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_list_all_trades(client):
    r = client.get("/api/v1/agent/trades", headers=_auth())
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_list_all_trades_filter_by_mode(client):
    r = client.get("/api/v1/agent/trades", params={"mode": "live"}, headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["mode"] == "live"
    assert body[0]["tx_hash"]


def test_list_all_trades_filter_by_strategy(client):
    r = client.get("/api/v1/agent/trades",
                   params={"strategy_id": "nonexistent"}, headers=_auth())
    assert r.status_code == 200
    assert r.json() == []


def test_auth_required_on_log_routes(client):
    assert client.get("/api/v1/agent/strategies/s1/evaluations").status_code == 401
    assert client.get("/api/v1/agent/strategies/s1/trades").status_code == 401
    assert client.get("/api/v1/agent/trades").status_code == 401
