"""Integration tests for discovery routes — /status and /tools."""
from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "disc.db"
    from src.config import app_config
    from src.services import scheduler_service as ss
    from src.shared.db import sqlite as db_mod

    monkeypatch.setattr(app_config, "DB_PATH", str(db_file))
    db_mod.reset_connection()
    ss.reset_scheduler_cache()

    from src.app import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c
    ss.reset_scheduler_cache()
    db_mod.reset_connection()


def test_status_returns_expected_shape(client):
    r = client.get("/api/v1/agent/status")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "0.1.0"
    assert body["wallets_count"] == 0
    assert set(body["strategies"].keys()) == {"draft", "inactive", "paper", "live", "archived"}
    assert body["active_cron_jobs"] == 0
    assert "db_path" in body
    assert body["uptime_seconds"] >= 0


def test_status_counts_wallets_and_strategies(client):
    from src.shared.db.sqlite import get_connection

    conn = get_connection()
    conn.execute(
        """INSERT INTO wallets (id, address, chain, network, chain_id,
           encrypted_secret, encryption_method, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        ("w1", "0xabc", "evm", "testnet", 84532, b"ct", "fernet-v1",
         "2026-04-20T00:00:00+00:00"),
    )
    for sid, status in [("s1", "paper"), ("s2", "live"), ("s3", "paper"), ("s4", "archived")]:
        conn.execute(
            """INSERT INTO strategies (id, mangrove_id, name, asset, timeframe, status,
               entry_json, exit_json, execution_config_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, f"mg-{sid}", sid, "ETH", "1h", status, "[]", "[]", "{}",
             "2026-04-20T00:00:00+00:00", "2026-04-20T00:00:00+00:00"),
        )
    conn.commit()

    body = client.get("/api/v1/agent/status").json()
    assert body["wallets_count"] == 1
    assert body["strategies"]["paper"] == 2
    assert body["strategies"]["live"] == 1
    assert body["strategies"]["archived"] == 1


def test_tools_returns_registered_catalog(client):
    r = client.get("/api/v1/agent/tools")
    assert r.status_code == 200
    body = r.json()
    assert "tools" in body
    assert isinstance(body["tools"], list)
    # hello_mangrove is registered from Phase 1; should be here.
    names = {t["name"] for t in body["tools"]}
    assert "hello_mangrove" in names


def test_discovery_endpoints_do_not_require_api_key(client):
    # No X-API-Key header.
    assert client.get("/api/v1/agent/status").status_code == 200
    assert client.get("/api/v1/agent/tools").status_code == 200
    assert client.get("/health").status_code == 200
