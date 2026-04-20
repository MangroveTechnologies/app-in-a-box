"""Integration tests for wallet routes — auth, CRUD, SDK pass-throughs."""
from __future__ import annotations

import os
from unittest.mock import MagicMock

os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402
from eth_account import Account  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_API_KEY = "test-key-1"
_TEST_PRIVKEY = "0x" + "11" * 32
_TEST_ADDRESS = Account.from_key(_TEST_PRIVKEY).address


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "wr.db"
    from src.config import app_config
    from src.services import scheduler_service as ss
    from src.shared.db import sqlite as db_mod

    monkeypatch.setattr(app_config, "DB_PATH", str(db_file))
    db_mod.reset_connection()
    ss.reset_scheduler_cache()

    # Stub keyring (no real keychain inside the container).
    store: dict = {}
    monkeypatch.setattr("keyring.get_password", lambda s, u: store.get((s, u)))
    monkeypatch.setattr("keyring.set_password",
                        lambda s, u, p: store.update({(s, u): p}))
    from src.shared.crypto import fernet as f
    f.reset_master_key_cache()

    # Stub SDK for wallet create + read endpoints.
    create_result = MagicMock()
    create_result.address = _TEST_ADDRESS
    create_result.private_key = _TEST_PRIVKEY
    create_result.seed_phrase = None
    create_result.secret = None

    sdk = MagicMock()
    sdk.wallet.create.return_value = create_result

    # dex.balances
    balances = MagicMock()
    balances.model_dump.return_value = {"balances": [{"token": "ETH", "amount": 1.5}]}
    sdk.dex.balances.return_value = balances

    # portfolio.*
    for attr, payload in [
        ("value", {"total_value_usd": 1000.0}),
        ("pnl", {"pnl_usd": 50.0}),
        ("tokens", {"tokens": []}),
        ("defi", {"positions": []}),
    ]:
        m = MagicMock()
        m.model_dump.return_value = payload
        setattr(sdk.portfolio, attr, MagicMock(return_value=m))
    sdk.portfolio.history.return_value = [MagicMock(model_dump=MagicMock(return_value={"tx": "0xabc"}))]

    monkeypatch.setattr("src.services.wallet_manager.mangrovemarkets_client", lambda: sdk)
    monkeypatch.setattr("src.api.routes.wallet.mangrovemarkets_client", lambda: sdk)

    from src.app import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c
    ss.reset_scheduler_cache()
    db_mod.reset_connection()
    f.reset_master_key_cache()


def _auth() -> dict:
    return {"X-API-Key": _API_KEY}


def test_create_wallet_happy_path(client):
    r = client.post(
        "/api/v1/agent/wallet/create",
        headers=_auth(),
        json={"chain": "evm", "network": "testnet", "chain_id": 84532, "label": "test"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["address"] == _TEST_ADDRESS
    assert body["chain"] == "evm"
    assert body["seed_phrase"] == _TEST_PRIVKEY  # one-time return
    assert "chat transcript" in body["warning"]


def test_create_wallet_xrpl_returns_501(client):
    r = client.post(
        "/api/v1/agent/wallet/create",
        headers=_auth(),
        json={"chain": "xrpl", "network": "testnet"},
    )
    assert r.status_code == 501
    assert r.json()["code"] == "CHAIN_NOT_SUPPORTED_IN_V1"


def test_auth_required(client):
    r = client.post(
        "/api/v1/agent/wallet/create",
        json={"chain": "evm", "network": "testnet", "chain_id": 84532},
    )
    assert r.status_code == 401
    assert r.json()["code"] in {"AUTH_MISSING_API_KEY", "AUTH_INVALID_API_KEY"}


def test_auth_rejects_bad_key(client):
    r = client.post(
        "/api/v1/agent/wallet/create",
        headers={"X-API-Key": "wrong-key"},
        json={"chain": "evm", "network": "testnet", "chain_id": 84532},
    )
    assert r.status_code == 401
    assert r.json()["code"] == "AUTH_INVALID_API_KEY"


def test_list_wallets_redacts_secrets(client):
    client.post(
        "/api/v1/agent/wallet/create",
        headers=_auth(),
        json={"chain": "evm", "network": "testnet", "chain_id": 84532, "label": "a"},
    )
    r = client.get("/api/v1/agent/wallet/list", headers=_auth())
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    for forbidden in ("secret", "seed_phrase", "private_key", "encrypted_secret"):
        assert forbidden not in items[0]


def test_balances_passes_through_to_sdk(client):
    r = client.get(
        f"/api/v1/agent/wallet/{_TEST_ADDRESS}/balances",
        params={"chain_id": 84532},
        headers=_auth(),
    )
    assert r.status_code == 200
    assert r.json() == {"balances": [{"token": "ETH", "amount": 1.5}]}


def test_portfolio_aggregates_sdk_calls(client):
    r = client.get(
        f"/api/v1/agent/wallet/{_TEST_ADDRESS}/portfolio",
        headers=_auth(),
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"value", "pnl", "tokens", "defi"}
    assert body["value"] == {"total_value_usd": 1000.0}


def test_history_passes_through_to_sdk(client):
    r = client.get(
        f"/api/v1/agent/wallet/{_TEST_ADDRESS}/history",
        params={"limit": 10},
        headers=_auth(),
    )
    assert r.status_code == 200
    assert r.json() == [{"tx": "0xabc"}]


def test_correlation_id_on_error_response(client):
    """Auth-rejected responses carry the spec-shaped error body with correlation_id."""
    r = client.post(
        "/api/v1/agent/wallet/create",
        json={"chain": "evm", "network": "testnet", "chain_id": 84532},
    )
    body = r.json()
    assert body["error"] is True
    assert "correlation_id" in body
    assert r.headers.get("x-correlation-id") == body["correlation_id"]
