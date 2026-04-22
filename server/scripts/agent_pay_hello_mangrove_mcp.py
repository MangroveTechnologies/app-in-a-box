"""Agent-native x402 payment over MCP — no human in the loop.

Mirror of agent_pay_hello_mangrove.py but for the MCP transport instead of
REST. Demonstrates the MCP-native x402 pattern used by the hello_mangrove
tool (`payment` parameter on the tool call) rather than the HTTP 402 +
X-PAYMENT header pattern used by the REST endpoint.

Flow:
    1. Connect to the MCP server at SERVER_URL/mcp/ via Streamable HTTP
    2. Call hello_mangrove() with empty payment -> receive payment requirements
       in the tool response body
    3. Sign an EIP-3009 payment authorization against those requirements
    4. Call hello_mangrove(payment=<base64>) -> receive the message plus
       settlement receipt (network, payer, transaction hash)

Requirements:
    - Server running (default: http://127.0.0.1:8080)
    - WALLET_SECRET env var with EVM private key funded on the active network
      (~$0.05 USDC + a few cents of ETH for gas on Base mainnet)

Usage:
    export WALLET_SECRET=0x...
    ENVIRONMENT=local python scripts/agent_pay_hello_mangrove_mcp.py

    SERVER_URL=http://127.0.0.1:8081 python scripts/agent_pay_hello_mangrove_mcp.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from eth_account import Account
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from x402 import x402Client
from x402.http.utils import encode_payment_signature_header
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.mechanisms.evm.signers import EthAccountSigner
from x402.schemas import PaymentRequired, ResourceInfo


def _parse_tool_result(result) -> dict:
    """Extract the first TextContent block and parse as JSON."""
    if not result.content:
        raise RuntimeError(f"Tool returned empty content: {result}")
    first = result.content[0]
    text = getattr(first, "text", None) or first.get("text", "")
    if not text:
        raise RuntimeError(f"No text in tool response: {result}")
    return json.loads(text)


async def main() -> int:
    secret = os.environ.get("WALLET_SECRET")
    if not secret:
        print("ERROR: WALLET_SECRET unset. Export an EVM private key.", file=sys.stderr)
        return 1

    base_url = os.environ.get("SERVER_URL", "http://127.0.0.1:8080").rstrip("/")
    mcp_url = f"{base_url}/mcp/"

    account = Account.from_key(secret)
    print(f"Payer address: {account.address}")
    print(f"MCP endpoint:  {mcp_url}")

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Step 1: call without payment; server returns requirements in body
            first = await session.call_tool("hello_mangrove", {})
            body = _parse_tool_result(first)
            if not body.get("error"):
                print("Unexpected: tool returned non-error on empty payment.")
                print(json.dumps(body, indent=2))
                return 1
            print(f"Unpaid call:  {body.get('code', '?')} — {body.get('message', '')}")

            payment_required = PaymentRequired.model_validate(body["payment_required_decoded"])
            first_accept = payment_required.accepts[0]
            print(f"Requirement:  {first_accept.amount} base units on {first_accept.network} -> {first_accept.pay_to}")

            # Step 2: sign a payment authorization against the requirements
            x402_client = x402Client()
            x402_client.register(
                first_accept.network,
                ExactEvmClientScheme(EthAccountSigner(account)),
            )
            payload = await x402_client.create_payment_payload(
                payment_required,
                resource=ResourceInfo(url=payment_required.resource.url),
            )
            signed = encode_payment_signature_header(payload)

            # Step 3: call again with payment attached as tool arg
            second = await session.call_tool("hello_mangrove", {"payment": signed})
            result = _parse_tool_result(second)

            if result.get("error"):
                print(f"Paid call failed: {result.get('code')} — {result.get('message')}")
                return 1

            print(f"Paid call:    {result.get('message', '(no message)')}")
            settlement = result.get("settlement", {})
            if settlement:
                tx = settlement.get("transaction", "")
                print(f"Payer:        {settlement.get('payer')}")
                print(f"Network:      {settlement.get('network')}")
                print(f"Transaction:  {tx}")
                if tx and str(settlement.get("network", "")).endswith(":8453"):
                    print(f"BaseScan:     https://basescan.org/tx/{tx}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
