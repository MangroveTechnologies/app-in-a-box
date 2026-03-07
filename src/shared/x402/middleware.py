"""x402 payment middleware for FastAPI routes and MCP tools.

The x402_payable decorator wraps an async function. On each call:
1. Check if caller has a valid API key -- if so, skip payment.
2. If no API key and no payment proof, return 402 payment requirements.
3. If payment proof provided, verify via facilitator, execute, settle.
"""
from __future__ import annotations

import hashlib
import json
from functools import wraps
from typing import Callable, Optional

from src.shared.auth.middleware import has_valid_api_key
from src.shared.x402.errors import PaymentNetworkMismatchError, SettlementFailedError, X402Error
from src.shared.x402.facilitator import FacilitatorClient
from src.shared.x402.models import PaymentProof, PaymentRequirements


def _error_response(code: str, message: str, suggestion: str = "") -> dict:
    return {"error": True, "code": code, "message": message, "suggestion": suggestion}


def _payment_required_response(requirements: PaymentRequirements) -> dict:
    return {
        "payment_required": True,
        "tool_name": requirements.tool_name,
        "tool_args_hash": requirements.tool_args_hash,
        "accepts": [opt.model_dump(by_alias=True) for opt in requirements.accepts],
    }


def _args_hash(kwargs: dict) -> str:
    canonical = json.dumps(kwargs, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def x402_payable(price_resolver: Callable[[dict], Optional[PaymentRequirements]]):
    """Decorator that makes an async function payable via x402. API key holders bypass payment."""
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, api_key: str | None = None, payment_proof: str | None = None, **kwargs):
            if has_valid_api_key(api_key):
                return await fn(*args, **kwargs)

            requirements = price_resolver(kwargs)
            if requirements is None:
                return await fn(*args, **kwargs)

            if payment_proof is None:
                return _payment_required_response(requirements)

            try:
                proof = PaymentProof.model_validate_json(payment_proof)
            except Exception:
                return _error_response("PAYMENT_INVALID", "Could not parse payment_proof JSON.", "Ensure payment_proof is a valid JSON string with scheme, network, and payload fields.")

            accepted_networks = {opt.network for opt in requirements.accepts}
            if proof.network not in accepted_networks:
                err = PaymentNetworkMismatchError(proof.network, sorted(accepted_networks))
                return _error_response(err.code, err.message, err.suggestion)

            client = FacilitatorClient.for_network(proof.network)
            try:
                await client.verify(proof, requirements)
            except X402Error as exc:
                return _error_response(exc.code, exc.message, exc.suggestion)

            result = await fn(*args, **kwargs)

            try:
                receipt = await client.settle(proof)
                if isinstance(result, dict):
                    result["settlement_receipt"] = receipt.model_dump()
                return result
            except SettlementFailedError:
                if isinstance(result, dict):
                    result["settlement_pending"] = True
                return result

        return wrapper
    return decorator
