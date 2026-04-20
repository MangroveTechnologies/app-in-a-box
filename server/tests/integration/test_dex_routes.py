"""Integration tests for DEX routes."""
from __future__ import annotations

import os
from unittest.mock import MagicMock

os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_API_KEY = "test-key-1"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "dex.db"
    from src.config import app_config
    from src.services import scheduler_service as ss
    from src.shared.db import sqlite as db_mod

    monkeypatch.setattr(app_config, "DB_PATH", str(db_file))
    db_mod.reset_connection()
    ss.reset_scheduler_cache()

    from src.shared.db.sqlite import get_connection, init_db
    init_db()

    # Seed a placeholder strategy row for user-initiated trades (FK target).
    get_connection().execute(
        """INSERT INTO strategies (id, mangrove_id, name, asset, timeframe, status,
           entry_json, exit_json, execution_config_json, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        ("user-initiated", "mg-user", "user", "ETH", "1h", "paper",
         "[]", "[]", "{}", "2026-04-20T00:00:00+00:00", "2026-04-20T00:00:00+00:00"),
    )
    get_connection().commit()

    # Stub the markets SDK (used by routes AND order_executor).
    sdk = MagicMock()

    venue = MagicMock()
    venue.model_dump.return_value = {"id": "uniswap-v2", "name": "Uniswap V2", "chain": "base"}
    sdk.dex.supported_venues.return_value = [venue]

    pair = MagicMock()
    pair.model_dump.return_value = {"from_token": "USDC", "to_token": "ETH"}
    sdk.dex.supported_pairs.return_value = [pair]

    quote = MagicMock()
    quote.model_dump.return_value = {
        "quote_id": "q-1", "input_amount": 100.0, "output_amount": 0.04,
        "exchange_rate": 2500.0,
    }
    quote.quote_id = "q-1"
    quote.output_amount = 0.04
    quote.exchange_rate = 2500.0
    quote.venue_fee = 0.0
    quote.mangrove_fee = 0.0
    quote.price_impact_percent = 0.0
    sdk.dex.get_quote.return_value = quote

    sdk.dex.approve_token.return_value = None  # already approved

    prepare = MagicMock()
    prepare.payload = {"chainId": 84532, "to": "0x" + "a" * 40, "data": "0x"}
    sdk.dex.prepare_swap.return_value = prepare

    bcast = MagicMock()
    bcast.tx_hash = "0xdeadbeef"
    sdk.dex.broadcast.return_value = bcast

    tx_status = MagicMock()
    tx_status.status = "confirmed"
    tx_status.block_number = 42
    tx_status.error_message = None
    sdk.dex.tx_status.return_value = tx_status

    monkeypatch.setattr("src.api.routes.dex.mangrovemarkets_client", lambda: sdk)
    monkeypatch.setattr("src.services.order_executor.mangrovemarkets_client", lambda: sdk)
    monkeypatch.setattr(
        "src.services.order_executor.wallet_sign",
        lambda payload, wallet_address, chain_id=None: "0xSIGNED",
    )

    from src.app import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c
    ss.reset_scheduler_cache()
    db_mod.reset_connection()


def _auth() -> dict:
    return {"X-API-Key": _API_KEY}


def test_venues(client):
    r = client.get("/api/v1/agent/dex/venues", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == "uniswap-v2"


def test_pairs(client):
    r = client.get("/api/v1/agent/dex/pairs", params={"venue_id": "uniswap-v2"}, headers=_auth())
    assert r.status_code == 200
    assert r.json()[0]["from_token"] == "USDC"


def test_quote(client):
    r = client.post(
        "/api/v1/agent/dex/quote",
        headers=_auth(),
        json={"input_token": "USDC", "output_token": "ETH", "amount": 100.0, "chain_id": 84532},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["quote_id"] == "q-1"
    assert body["output_amount"] == 0.04


def test_swap_requires_confirm(client):
    r = client.post(
        "/api/v1/agent/dex/swap",
        headers=_auth(),
        json={
            "input_token": "USDC", "output_token": "ETH", "amount": 100.0,
            "chain_id": 84532, "wallet_address": "0xabc", "confirm": False,
        },
    )
    assert r.status_code == 400
    assert r.json()["code"] == "CONFIRMATION_REQUIRED"


def test_swap_happy_path(client):
    r = client.post(
        "/api/v1/agent/dex/swap",
        headers=_auth(),
        json={
            "input_token": "USDC", "output_token": "ETH", "amount": 100.0,
            "chain_id": 84532, "wallet_address": "0xabc", "confirm": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tx_hash"] == "0xdeadbeef"
    assert body["status"] == "confirmed"
    assert body["input_token"] == "USDC"
    assert body["output_token"] == "ETH"
    assert "trade_log_id" in body


def test_auth_required_on_dex_endpoints(client):
    assert client.get("/api/v1/agent/dex/venues").status_code == 401
    assert client.get("/api/v1/agent/dex/pairs?venue_id=x").status_code == 401
    assert client.post("/api/v1/agent/dex/quote",
                       json={"input_token": "USDC", "output_token": "ETH",
                             "amount": 1, "chain_id": 84532}).status_code == 401
