"""Interactive x402 payment script.

Step through the x402 payment flow manually. All config values are loaded
from the app's config system (src/config/{ENVIRONMENT}-config.json).

Usage:
    ENVIRONMENT=local python scripts/pay_easter_egg.py

Requires:
    - src/config/local-config.json with x402 settings
    - WALLET_SECRET env var set to a funded EVM private key
"""
import asyncio
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("ENVIRONMENT", "local")


def load_wallet_secret():
    """Load wallet secret from WALLET_SECRET env var."""
    return os.environ.get("WALLET_SECRET")


def setup_server():
    """Create the FastAPI app with x402 middleware using app config."""
    from fastapi import FastAPI, Request
    from x402 import x402ResourceServer
    from x402.http import HTTPFacilitatorClient
    from x402.http.facilitator_client_base import CreateHeadersAuthProvider, FacilitatorConfig
    from x402.http.middleware.fastapi import payment_middleware
    from x402.http.types import PaymentOption as HTTPPaymentOption
    from x402.http.types import RouteConfig
    from x402.mechanisms.evm.exact import register_exact_evm_server
    from x402.mechanisms.evm.exact.server import ExactEvmScheme

    from src.shared.x402.config import (
        get_cdp_api_key_id,
        get_cdp_api_key_secret,
        get_facilitator_url,
        get_network,
        get_pay_to,
    )

    facilitator_url = get_facilitator_url()
    network = get_network()
    pay_to = get_pay_to()

    # Build CDP auth if keys configured
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

    return app


async def main():
    from src.shared.x402.config import get_facilitator_url, get_network, get_pay_to

    wallet_secret = load_wallet_secret()
    if not wallet_secret:
        print("ERROR: WALLET_SECRET not found.")
        sys.exit(1)

    print()
    print("  x402 Payment Flow -- Step by Step")
    print("  ==================================")
    print(f"  Network:     {get_network()}")
    print(f"  Facilitator: {get_facilitator_url()}")
    print(f"  Pay to:      {get_pay_to()}")
    print()

    print("  Loading server...")
    app = setup_server()
    print("  Ready.")
    print()

    import httpx
    from eth_account import Account

    account = Account.from_key(wallet_secret)
    asgi = httpx.ASGITransport(app=app)

    # -- Step 1 --
    input("  Step 1: Hit /api/x402/easter-egg with NO credentials. Press Enter...")
    print()

    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
        resp = await client.get("/api/x402/easter-egg")

    print(f"  Response: HTTP {resp.status_code}")
    if resp.status_code == 402:
        print("  --> Server says: PAYMENT REQUIRED")
        payment_header = resp.headers.get("payment-required", "")
        if payment_header:
            padded = payment_header + "=" * (4 - len(payment_header) % 4)
            reqs = json.loads(base64.b64decode(padded))
            accept = reqs["accepts"][0]
            print(f"  --> Network: {accept['network']}")
            print(f"  --> Pay to:  {accept['payTo']}")
            amt = accept.get("maxAmountRequired", "?")
            if amt != "?":
                print(f"  --> Amount:  {amt} base units = ${int(amt)/1_000_000:.2f} USDC")
    print()

    # -- Step 2 --
    print(f"  Step 2: Pay $0.05 USDC from {account.address}")
    input("  This costs REAL MONEY on mainnet. Press Enter to proceed (Ctrl+C to abort)...")
    print()

    from x402 import x402Client
    from x402.http.clients.httpx import x402AsyncTransport
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.mechanisms.evm.signers import EthAccountSigner

    x402_client = x402Client()
    register_exact_evm_client(x402_client, EthAccountSigner(account))
    x402_transport = x402AsyncTransport(x402_client, transport=asgi)

    print("  Signing payment and sending...")
    async with httpx.AsyncClient(transport=x402_transport, base_url="http://test") as client:
        resp = await client.get("/api/x402/easter-egg")

    print()
    print(f"  Response: HTTP {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Message: {data['message']}")
        print()

        pr = resp.headers.get("payment-response") or resp.headers.get("x-payment-response")
        if pr:
            padded = pr + "=" * (4 - len(pr) % 4)
            settlement = json.loads(base64.b64decode(padded))
            print("  Settlement:")
            print(f"    Payer:       {settlement.get('payer', 'N/A')}")
            print(f"    Network:     {settlement.get('network', 'N/A')}")
            print(f"    Transaction: {settlement.get('transaction', 'N/A')}")
            tx = settlement.get("transaction", "")
            if tx:
                print()
                print(f"  View on BaseScan: https://basescan.org/tx/{tx}")
    else:
        print(f"  Failed: {resp.text[:300]}")

    print()
    print("  Done.")


if __name__ == "__main__":
    asyncio.run(main())
