"""Agent-native x402 payment — no human in the loop.

Demonstrates the canonical agent pattern: hit the endpoint, let the x402
client transport auto-handle the 402, and get the settlement tx back in
one call. Mirrors what any MCP client or LLM agent would do to pay for
a service on its own.

Contrast with pay_hello_mangrove.py, which is an interactive step-through
for humans learning the protocol.

Requirements:
    - Server running (default: http://127.0.0.1:8080)
    - WALLET_SECRET env var with an EVM private key funded on the active
      network (~$0.05 USDC + a few cents of ETH for gas on Base mainnet)

Usage:
    export WALLET_SECRET=0x...
    ENVIRONMENT=local python scripts/agent_pay_hello_mangrove.py

    # Point at a non-default host:
    SERVER_URL=http://127.0.0.1:8081 python scripts/agent_pay_hello_mangrove.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys

import httpx
from eth_account import Account
from x402 import x402Client
from x402.http.clients.httpx import x402AsyncTransport
from x402.mechanisms.evm.exact import register_exact_evm_client
from x402.mechanisms.evm.signers import EthAccountSigner


def _decode_settlement(header: str) -> dict:
    padded = header + "=" * (-len(header) % 4)
    return json.loads(base64.b64decode(padded))


async def main() -> int:
    secret = os.environ.get("WALLET_SECRET")
    if not secret:
        print("ERROR: WALLET_SECRET unset. Export an EVM private key.", file=sys.stderr)
        return 1

    base_url = os.environ.get("SERVER_URL", "http://127.0.0.1:8080")
    account = Account.from_key(secret)
    print(f"Payer address: {account.address}")
    print(f"Server:        {base_url}")

    x402_client = x402Client()
    register_exact_evm_client(x402_client, EthAccountSigner(account))
    transport = x402AsyncTransport(x402_client, transport=httpx.AsyncHTTPTransport())

    async with httpx.AsyncClient(transport=transport, base_url=base_url, timeout=60.0) as client:
        resp = await client.get("/api/x402/hello-mangrove")

    print(f"HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text[:600])
        return 1

    print(f"Body: {resp.json()}")
    pr = resp.headers.get("payment-response") or resp.headers.get("x-payment-response")
    if not pr:
        print("Warning: no payment-response header on 200 response.")
        return 0

    settlement = _decode_settlement(pr)
    tx = settlement.get("transaction", "")
    print(f"Payer:       {settlement.get('payer')}")
    print(f"Network:     {settlement.get('network')}")
    print(f"Transaction: {tx}")
    if tx and settlement.get("network", "").endswith(":8453"):
        print(f"BaseScan:    https://basescan.org/tx/{tx}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
