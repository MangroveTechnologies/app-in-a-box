"""Easter egg endpoint tests (x402-gated).

The official x402 middleware handles payment flow:
- No credentials -> 402 with payment-required header
- API key -> 200 (bypasses middleware)
- Invalid payment signature -> 402 (correctly rejected by facilitator)
"""
import os
os.environ.setdefault("ENVIRONMENT", "test")

import base64
import json


def test_easter_egg_without_credentials_returns_402(client):
    resp = client.get("/api/v1/easter-egg")
    assert resp.status_code == 402

    # Official x402 middleware returns payment requirements in header
    payment_header = resp.headers.get("payment-required")
    assert payment_header is not None, "Missing payment-required header"

    # Decode and verify the payment requirements
    padded = payment_header + "=" * (4 - len(payment_header) % 4)
    requirements = json.loads(base64.b64decode(padded))
    assert requirements["x402Version"] == 2
    assert len(requirements["accepts"]) >= 1
    accept = requirements["accepts"][0]
    assert accept["payTo"] == "0xdAC6843ccA8B8c127d9d10EdB327fb0ddb2a5576"


def test_easter_egg_with_api_key_returns_message(client):
    resp = client.get("/api/v1/easter-egg", headers={"X-API-Key": "test-key-1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "Thank you for supporting the project" in data["message"]
    assert "timestamp" in data


def test_easter_egg_invalid_payment_returns_402(client):
    """Mock/invalid payment signatures are correctly rejected by the real middleware."""
    resp = client.get(
        "/api/v1/easter-egg",
        headers={"Payment-Signature": "invalid-signature"},
    )
    # Real middleware rejects invalid signatures -- this is correct behavior
    assert resp.status_code == 402
