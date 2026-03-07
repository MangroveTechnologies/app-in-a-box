"""Easter egg endpoint tests (x402-gated)."""
import os
os.environ.setdefault("ENVIRONMENT", "test")


def test_easter_egg_without_credentials_returns_402(client):
    resp = client.get("/api/v1/easter-egg")
    assert resp.status_code == 402
    data = resp.json()
    assert data["payment_required"] is True
    assert len(data["accepts"]) == 1
    assert data["accepts"][0]["network"] == "base"
    assert data["accepts"][0]["maxAmountRequired"] == "50000"
    assert data["accepts"][0]["payTo"] == "0xdAC6843ccA8B8c127d9d10EdB327fb0ddb2a5576"


def test_easter_egg_with_api_key_returns_message(client):
    resp = client.get("/api/v1/easter-egg", headers={"X-API-Key": "test-key-1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "Thank you for supporting the project" in data["message"]
    assert "timestamp" in data


def test_easter_egg_with_payment_signature(client):
    resp = client.get(
        "/api/v1/easter-egg",
        headers={"X-Payment-Signature": "mock-signature"},
    )
    assert resp.status_code == 200
    assert "Thank you" in resp.json()["message"]
