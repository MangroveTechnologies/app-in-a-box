"""Simple interactive x402 payment script.

Step through the x402 payment flow manually to see exactly what happens.

Usage:
    python scripts/pay_easter_egg.py

Requires:
    - MangroveMarkets/.env with WALLET_SECRET
    - MangroveMarkets-MCP-Server/src/shared/config/local-config.json with CDP_API_KEY_ID + CDP_API_KEY_SECRET
"""
import asyncio
import base64
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse


def load_secrets():
    """Load CDP keys and wallet secret from sibling project configs."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # CDP keys from MCP-Server
    config_path = os.path.join(base, "MangroveMarkets-MCP-Server", "src", "shared", "config", "local-config.json")
    with open(config_path) as f:
        config = json.load(f)

    # Wallet secret from MangroveMarkets
    env_path = os.path.join(base, "MangroveMarkets", ".env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                value = value.strip().strip('"').strip("'")
                if key.strip() == "WALLET_SECRET":
                    config["WALLET_SECRET"] = value

    return config


def setup_server():
    """Create the FastAPI app with x402 middleware."""
    from fastapi import FastAPI, Request
    from x402.http.middleware.fastapi import payment_middleware
    from x402.http import HTTPFacilitatorClient
    from x402.http.facilitator_client_base import FacilitatorConfig, CreateHeadersAuthProvider
    from x402 import x402ResourceServer
    from x402.mechanisms.evm.exact import register_exact_evm_server
    from x402.mechanisms.evm.exact.server import ExactEvmScheme
    from cdp.auth import get_auth_headers, GetAuthHeadersOptions

    config = load_secrets()
    CDP_URL = "https://api.cdp.coinbase.com/platform/v2/x402"
    PAY_TO = "0xdAC6843ccA8B8c127d9d10EdB327fb0ddb2a5576"
    parsed = urlparse(CDP_URL)

    def create_headers():
        headers_map = {}
        for endpoint, method in [("verify", "POST"), ("settle", "POST"), ("supported", "GET")]:
            path = f"{parsed.path}/{endpoint}"
            h = get_auth_headers(GetAuthHeadersOptions(
                api_key_id=config["CDP_API_KEY_ID"],
                api_key_secret=config["CDP_API_KEY_SECRET"],
                request_method=method,
                request_host=parsed.hostname,
                request_path=path,
            ))
            headers_map[endpoint] = h
        headers_map["list"] = headers_map.pop("supported")
        return headers_map

    auth = CreateHeadersAuthProvider(create_headers)
    facilitator = HTTPFacilitatorClient(config=FacilitatorConfig(url=CDP_URL, auth_provider=auth))
    server = x402ResourceServer(facilitator)
    register_exact_evm_server(server)
    server.register("base", ExactEvmScheme())

    routes = {
        "GET /api/v1/easter-egg": {
            "accepts": {
                "scheme": "exact",
                "network": "eip155:8453",
                "payTo": PAY_TO,
                "price": "$0.05",
            },
        },
    }

    app = FastAPI()
    mw = payment_middleware(routes, server)

    @app.middleware("http")
    async def x402_mw(request: Request, call_next):
        return await mw(request, call_next)

    @app.get("/api/v1/easter-egg")
    async def easter_egg():
        return {
            "message": "Thank you for supporting the project and strengthening the ecosystem",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return app, config


async def main():
    print()
    print("  x402 Payment Flow -- Step by Step")
    print("  ==================================")
    print()

    # -- Setup --
    print("  Loading config and creating server...")
    app, config = setup_server()
    print("  Done.")
    print()

    import httpx
    from eth_account import Account

    account = Account.from_key(config["WALLET_SECRET"])
    asgi = httpx.ASGITransport(app=app)

    # -- Step 1: Hit the endpoint with no credentials --
    input("  Step 1: Hit /api/v1/easter-egg with NO credentials. Press Enter...")
    print()

    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
        resp = await client.get("/api/v1/easter-egg")

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
            print(f"  --> Asset:   {accept.get('asset', 'USDC')}")
            amt = accept.get("maxAmountRequired", "?")
            print(f"  --> Amount:  {amt} base units = ${int(amt)/1_000_000:.2f} USDC")
    print()

    # -- Step 2: Hit with API key --
    input("  Step 2: Hit with API key (free access for subscribers). Press Enter...")
    print()

    # Note: middleware doesn't check API keys -- that's app-level.
    # For this demo, we show the payment path only.
    print("  (API key bypass is handled by the app middleware, not shown in this script)")
    print()

    # -- Step 3: Pay with x402 --
    print(f"  Step 3: Pay $0.05 USDC on Base mainnet from {account.address}")
    input("  This costs REAL MONEY. Press Enter to proceed (or Ctrl+C to abort)...")
    print()

    from x402 import x402Client
    from x402.mechanisms.evm.signers import EthAccountSigner
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.http.clients.httpx import x402AsyncTransport

    x402_client = x402Client()
    register_exact_evm_client(x402_client, EthAccountSigner(account))

    x402_transport = x402AsyncTransport(x402_client, transport=asgi)

    print("  Signing payment and sending...")
    async with httpx.AsyncClient(transport=x402_transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/easter-egg")

    print()
    print(f"  Response: HTTP {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Message: {data['message']}")
        print()

        # Settlement info
        pr = resp.headers.get("payment-response") or resp.headers.get("x-payment-response")
        if pr:
            padded = pr + "=" * (4 - len(pr) % 4)
            settlement = json.loads(base64.b64decode(padded))
            print("  Settlement details:")
            print(f"    Payer:       {settlement.get('payer', 'N/A')}")
            print(f"    Network:     {settlement.get('network', 'N/A')}")
            print(f"    Transaction: {settlement.get('transaction', 'N/A')}")
            print(f"    Success:     {settlement.get('success', 'N/A')}")
            tx = settlement.get("transaction", "")
            if tx:
                print()
                print(f"  View on BaseScan: https://basescan.org/tx/{tx}")
                print(f"  (Look for USDC token transfer, not ETH -- the facilitator sends the tx)")
    else:
        print(f"  Failed: {resp.text[:300]}")

    print()
    print("  Done.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
