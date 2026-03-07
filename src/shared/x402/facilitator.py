"""Async HTTP client for x402 facilitator endpoints."""
from __future__ import annotations

import httpx

from src.shared.x402.errors import FacilitatorUnreachableError, PaymentInvalidError, SettlementFailedError
from src.shared.x402.models import PaymentProof, PaymentRequirements, SettlementReceipt

_DEFAULT_FACILITATOR_URLS: dict[str, str] = {
    "base": "https://x402.org/facilitator",
    "base-sepolia": "https://x402.org/facilitator",
}

_DEFAULT_VERIFY_TIMEOUT = 10.0
_DEFAULT_SETTLE_TIMEOUT = 30.0


class FacilitatorClient:
    def __init__(self, base_url: str, verify_timeout: float = _DEFAULT_VERIFY_TIMEOUT, settle_timeout: float = _DEFAULT_SETTLE_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.verify_timeout = verify_timeout
        self.settle_timeout = settle_timeout

    @classmethod
    def for_network(cls, network: str, **kwargs) -> FacilitatorClient:
        url = kwargs.pop("base_url", None) or _DEFAULT_FACILITATOR_URLS.get(network)
        if url is None:
            raise ValueError(f"Unsupported network '{network}'. Known: {list(_DEFAULT_FACILITATOR_URLS.keys())}")
        return cls(base_url=url, **kwargs)

    async def verify(self, proof: PaymentProof, requirements: PaymentRequirements) -> bool:
        payload = {"proof": proof.model_dump(), "requirements": requirements.model_dump()}
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.post(f"{self.base_url}/verify", json=payload, timeout=self.verify_timeout)
        except (httpx.TimeoutException, httpx.ConnectError):
            raise FacilitatorUnreachableError(self.base_url)
        if resp.status_code >= 500:
            raise FacilitatorUnreachableError(self.base_url)
        data = resp.json()
        if resp.status_code >= 400:
            raise PaymentInvalidError(data.get("error", data.get("reason", "rejected")))
        if not data.get("valid", False):
            raise PaymentInvalidError(data.get("reason", "verification failed"))
        return True

    async def settle(self, proof: PaymentProof) -> SettlementReceipt:
        payload = {"proof": proof.model_dump()}
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.post(f"{self.base_url}/settle", json=payload, timeout=self.settle_timeout)
        except (httpx.TimeoutException, httpx.ConnectError):
            raise SettlementFailedError("facilitator timed out or unreachable")
        if resp.status_code >= 400:
            raise SettlementFailedError(resp.json().get("error", "settlement rejected"))
        return SettlementReceipt.model_validate(resp.json())
