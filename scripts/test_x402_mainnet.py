"""End-to-end x402 MAINNET payment test.

Tests real $0.05 USDC payment on Base mainnet via CDP facilitator.
This costs real money (test USDC on Base Sepolia is free, this is not).

Flow:
1. Start FastAPI server with x402 middleware (CDP facilitator, Base mainnet)
2. Client hits easter-egg endpoint -> gets 402
3. x402 SDK auto-signs payment with wallet
4. Server verifies via CDP facilitator -> content delivered -> settled on-chain

Requirements:
- CDP_API_KEY_ID and CDP_API_KEY_SECRET in MCP-Server local-config.json
- WALLET_SECRET in MangroveMarkets/.env (wallet with USDC on Base mainnet)

Usage:
    python scripts/test_x402_mainnet.py
"""
import asyncio
import json
import os
import sys
from urllib.parse import urlparse

# -- Config --
MCP_SERVER_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "MangroveMarkets-MCP-Server", "src", "shared", "config", "local-config.json",
)
MANGROVE_MARKETS_ENV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "MangroveMarkets", ".env",
)

PAY_TO = "0xdAC6843ccA8B8c127d9d10EdB327fb0ddb2a5576"
USDC_BASE_MAINNET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CDP_FACILITATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402"


def load_config():
    """Load CDP API keys from MCP-Server config and wallet secret from MangroveMarkets."""
    with open(MCP_SERVER_CONFIG) as f:
        config = json.load(f)

    # Load wallet secret
    with open(MANGROVE_MARKETS_ENV) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                value = value.strip().strip('"').strip("'")
                if key.strip() == "WALLET_SECRET":
                    config["WALLET_SECRET"] = value

    return config


def create_cdp_auth_provider(api_key_id: str, api_key_secret: str):
    """Create an AuthProvider for the CDP facilitator using JWT signing."""
    from cdp.auth import get_auth_headers, GetAuthHeadersOptions
    from x402.http.facilitator_client_base import CreateHeadersAuthProvider

    parsed = urlparse(CDP_FACILITATOR_URL)

    def create_headers():
        """Generate fresh JWT headers for each facilitator request."""
        headers_map = {}
        for endpoint, method in [("verify", "POST"), ("settle", "POST"), ("supported", "GET")]:
            path = f"{parsed.path}/{endpoint}"
            h = get_auth_headers(GetAuthHeadersOptions(
                api_key_id=api_key_id,
                api_key_secret=api_key_secret,
                request_method=method,
                request_host=parsed.hostname,
                request_path=path,
            ))
            headers_map[endpoint] = h
        # Map "supported" to "list" key as expected by CreateHeadersAuthProvider
        headers_map["list"] = headers_map.pop("supported")
        return headers_map

    return CreateHeadersAuthProvider(create_headers)


async def main():
    config = load_config()

    if "WALLET_SECRET" not in config:
        print("ERROR: WALLET_SECRET not found in MangroveMarkets/.env")
        sys.exit(1)
    if "CDP_API_KEY_ID" not in config:
        print("ERROR: CDP_API_KEY_ID not found in MCP-Server local-config.json")
        sys.exit(1)

    print("=" * 60)
    print("x402 MAINNET Payment Test")
    print("Network: Base mainnet")
    print(f"Facilitator: {CDP_FACILITATOR_URL}")
    print(f"Pay to: {PAY_TO}")
    print("Price: $0.05 USDC (REAL MONEY)")
    print("=" * 60)
    print()

    # -- Step 1: Create server app with CDP facilitator --
    print("--- Step 1: Create server with CDP facilitator ---")
    from fastapi import FastAPI, Request
    from x402.http.middleware.fastapi import payment_middleware
    from x402.http import HTTPFacilitatorClient
    from x402.http.facilitator_client_base import FacilitatorConfig
    from x402 import x402ResourceServer
    from x402.mechanisms.evm.exact import register_exact_evm_server
    from datetime import datetime, timezone

    auth_provider = create_cdp_auth_provider(
        config["CDP_API_KEY_ID"],
        config["CDP_API_KEY_SECRET"],
    )

    facilitator = HTTPFacilitatorClient(config=FacilitatorConfig(
        url=CDP_FACILITATOR_URL,
        auth_provider=auth_provider,
    ))

    server = x402ResourceServer(facilitator)
    register_exact_evm_server(server)
    # Also register V1 network names (CDP facilitator uses "base" not "eip155:8453")
    from x402.mechanisms.evm.exact.server import ExactEvmScheme as ExactEvmServerScheme
    v1_scheme = ExactEvmServerScheme()
    server.register("base", v1_scheme)
    server.register("base-sepolia", v1_scheme)

    from x402.http.types import RouteConfig, PaymentOption as HTTPPaymentOption

    routes = {
        "GET /api/v1/easter-egg": RouteConfig(
            accepts=HTTPPaymentOption(
                scheme="exact",
                network="eip155:8453",
                pay_to=PAY_TO,
                price="$0.05",
            ),
        ),
    }

    app = FastAPI()
    mw = payment_middleware(routes, server, sync_facilitator_on_start=True)

    @app.middleware("http")
    async def x402_mw(request: Request, call_next):
        try:
            return await mw(request, call_next)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"MIDDLEWARE ERROR:\n{tb}")
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=500, content={"error": str(e), "traceback": tb})

    @app.get("/api/v1/easter-egg")
    async def easter_egg():
        return {
            "message": "Thank you for supporting the project and strengthening the ecosystem",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payment": "verified and settled on Base mainnet",
        }

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    print("  Server created with CDP facilitator (Base mainnet)")

    # -- Step 2: Verify 402 response --
    print()
    print("--- Step 2: Verify 402 response ---")
    from fastapi.testclient import TestClient
    import base64

    with TestClient(app, raise_server_exceptions=True) as client:
        resp = client.get("/api/v1/easter-egg")
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
        print(f"  Amount: {accept.get('maxAmountRequired', 'N/A')}")
        print("  PASS: Server returns 402 with Base mainnet payment requirements")

    # -- Step 3: Make real paid request using x402 httpx transport via TestClient --
    print()
    print("--- Step 3: Make REAL paid request ($0.05 USDC on Base mainnet) ---")
    from eth_account import Account
    from x402 import x402Client
    from x402.mechanisms.evm.signers import EthAccountSigner
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.http.clients.httpx import x402AsyncTransport
    import httpx

    account = Account.from_key(config["WALLET_SECRET"])
    print(f"  Wallet: {account.address}")

    x402_client = x402Client()
    register_exact_evm_client(x402_client, EthAccountSigner(account))

    # Use ASGI transport so we don't need a running server
    asgi_transport = httpx.ASGITransport(app=app)
    # Wrap ASGI transport with x402 payment handling
    x402_transport = x402AsyncTransport(x402_client, transport=asgi_transport)

    print("  Sending payment...")
    async with httpx.AsyncClient(transport=x402_transport, base_url="http://testserver") as http:
        resp = await http.get("/api/v1/easter-egg")

    print(f"  Status: {resp.status_code}")
    print(f"  Body: {resp.text[:500]}")

    # Check settlement header
    payment_response = resp.headers.get("payment-response") or resp.headers.get("x-payment-response")
    if payment_response:
        padded = payment_response + "=" * (4 - len(payment_response) % 4)
        try:
            settlement = json.loads(base64.b64decode(padded))
            print(f"  Settlement: {json.dumps(settlement, indent=2)}")
        except Exception:
            print(f"  Settlement header (raw): {payment_response[:200]}")

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Message: {data.get('message')}")
        print()
        print("=" * 60)
        print("MAINNET PAYMENT VERIFIED")
        print(f"$0.05 USDC moved from {account.address}")
        print(f"to {PAY_TO} on Base mainnet")
        print("Verified and settled by CDP facilitator")
        print("=" * 60)
    else:
        print(f"  FAIL: Expected 200 after payment, got {resp.status_code}")
        print("  Check wallet USDC balance on Base mainnet")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
