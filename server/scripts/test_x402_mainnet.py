"""End-to-end x402 payment test.

Tests a real USDC payment via the x402 protocol using the facilitator
and network configured in the app's config file.

Flow:
1. Loads config from src/config/{ENVIRONMENT}-config.json (same as the app)
2. Creates a FastAPI app with x402 middleware
3. Client hits easter-egg endpoint -> gets 402 with payment requirements
4. x402 SDK auto-signs payment with wallet
5. Server verifies via facilitator -> content delivered -> settled on-chain

Requirements:
- src/config/local-config.json exists with x402 settings
- WALLET_SECRET env var set to a funded EVM private key

Usage:
    WALLET_SECRET=0x... python scripts/test_x402_mainnet.py
"""
import asyncio
import base64
import json
import os
import sys

# Ensure we can import from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Set environment before importing config
os.environ.setdefault("ENVIRONMENT", "local")


def load_wallet_secret():
    """Load wallet secret from WALLET_SECRET env var."""
    return os.environ.get("WALLET_SECRET")


async def main():
    # Load app config (same config the app uses)
    from src.shared.x402.config import (
        get_cdp_api_key_id,
        get_cdp_api_key_secret,
        get_easter_egg_price,
        get_facilitator_url,
        get_network,
        get_pay_to,
    )

    wallet_secret = load_wallet_secret()
    if not wallet_secret:
        print("ERROR: WALLET_SECRET not found.")
        print("Export WALLET_SECRET=0x... before running this script")
        sys.exit(1)

    facilitator_url = get_facilitator_url()
    network = get_network()
    pay_to = get_pay_to()

    print("=" * 60)
    print("x402 End-to-End Payment Test")
    print(f"  Network:     {network}")
    print(f"  Facilitator: {facilitator_url}")
    print(f"  Pay to:      {pay_to}")
    print(f"  Price:       {get_easter_egg_price()} base units ($0.05 USDC)")
    print("=" * 60)
    print()

    # -- Step 1: Create server app with x402 middleware --
    print("--- Step 1: Create server ---")

    from fastapi import FastAPI, Request
    from x402 import x402ResourceServer
    from x402.http import HTTPFacilitatorClient
    from x402.http.facilitator_client_base import CreateHeadersAuthProvider, FacilitatorConfig
    from x402.http.middleware.fastapi import payment_middleware
    from x402.http.types import PaymentOption as HTTPPaymentOption
    from x402.http.types import RouteConfig
    from x402.mechanisms.evm.exact import register_exact_evm_server
    from x402.mechanisms.evm.exact.server import ExactEvmScheme

    # Build auth provider if CDP keys are configured
    auth_provider = None
    cdp_key_id = get_cdp_api_key_id()
    cdp_key_secret = get_cdp_api_key_secret()
    if cdp_key_id and cdp_key_secret:
        from urllib.parse import urlparse

        from cdp.auth import GetAuthHeadersOptions, get_auth_headers
        parsed = urlparse(facilitator_url)

        def create_headers():
            headers_map = {}
            for endpoint, method in [("verify", "POST"), ("settle", "POST"), ("supported", "GET")]:
                path = f"{parsed.path}/{endpoint}"
                h = get_auth_headers(GetAuthHeadersOptions(
                    api_key_id=cdp_key_id, api_key_secret=cdp_key_secret,
                    request_method=method, request_host=parsed.hostname, request_path=path,
                ))
                headers_map[endpoint] = h
            headers_map["list"] = headers_map.pop("supported")
            return headers_map

        auth_provider = CreateHeadersAuthProvider(create_headers)
        print("  CDP auth configured")

    fc_config = FacilitatorConfig(url=facilitator_url)
    if auth_provider:
        fc_config = FacilitatorConfig(url=facilitator_url, auth_provider=auth_provider)

    facilitator = HTTPFacilitatorClient(config=fc_config)
    server = x402ResourceServer(facilitator)
    register_exact_evm_server(server)
    server.register("base", ExactEvmScheme())
    server.register("base-sepolia", ExactEvmScheme())

    routes = {
        "GET /api/x402/easter-egg": RouteConfig(
            accepts=HTTPPaymentOption(
                scheme="exact", network=network, pay_to=pay_to, price="$0.05",
            ),
        ),
    }

    app = FastAPI()
    mw = payment_middleware(routes, server)

    @app.middleware("http")
    async def x402_mw(request: Request, call_next):
        return await mw(request, call_next)

    @app.get("/api/x402/easter-egg")
    async def easter_egg():
        from src.services.easter_egg import get_easter_egg
        return get_easter_egg()

    print("  Server created")

    # -- Step 2: Verify 402 response --
    print()
    print("--- Step 2: Verify 402 response ---")
    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/x402/easter-egg")
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 500:
            print(f"  Server error: {resp.text[:500]}")
            sys.exit(1)
        assert resp.status_code == 402, f"Expected 402, got {resp.status_code}"

        payment_header = resp.headers.get("payment-required")
        assert payment_header, "Missing payment-required header"
        padded = payment_header + "=" * (4 - len(payment_header) % 4)
        requirements = json.loads(base64.b64decode(padded))
        accept = requirements["accepts"][0]
        print(f"  Network: {accept['network']}")
        print(f"  Pay to: {accept['payTo']}")
        print("  PASS")

    # -- Step 3: Make paid request --
    print()
    print("--- Step 3: Make paid request ---")
    import httpx
    from eth_account import Account
    from x402 import x402Client
    from x402.http.clients.httpx import x402AsyncTransport
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.mechanisms.evm.signers import EthAccountSigner

    account = Account.from_key(wallet_secret)
    print(f"  Wallet: {account.address}")

    x402_client = x402Client()
    register_exact_evm_client(x402_client, EthAccountSigner(account))

    asgi_transport = httpx.ASGITransport(app=app)
    x402_transport = x402AsyncTransport(x402_client, transport=asgi_transport)

    print("  Sending payment...")
    async with httpx.AsyncClient(transport=x402_transport, base_url="http://testserver") as http:
        resp = await http.get("/api/x402/easter-egg")

    print(f"  Status: {resp.status_code}")

    payment_response = resp.headers.get("payment-response") or resp.headers.get("x-payment-response")
    if payment_response:
        padded = payment_response + "=" * (4 - len(payment_response) % 4)
        try:
            settlement = json.loads(base64.b64decode(padded))
            print(f"  Settlement: {json.dumps(settlement, indent=2)}")
        except Exception:
            print(f"  Settlement header: {payment_response[:200]}")

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Message: {data.get('message')}")
        print()
        print("=" * 60)
        print("PAYMENT VERIFIED")
        print(f"  From:    {account.address}")
        print(f"  To:      {pay_to}")
        print(f"  Network: {network}")
        if payment_response:
            print(f"  Tx:      {settlement.get('transaction', 'N/A')}")
        print("=" * 60)
    else:
        print(f"  FAIL: Expected 200, got {resp.status_code}")
        print(f"  Body: {resp.text[:300]}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
