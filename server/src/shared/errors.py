"""Agent error hierarchy and FastAPI exception handler.

All domain errors inherit from AgentError, which carries:
- code: short uppercase identifier (e.g. WALLET_NOT_FOUND)
- message: human-readable description
- suggestion: what to do about it (optional)
- http_status: HTTP status code for REST responses
- correlation_id: UUID, auto-generated unless provided

The response shape (enforced by agent_error_handler) is:
    {
        "error": true,
        "code": "ERROR_CODE",
        "message": "...",
        "suggestion": "...",   # null if not provided
        "correlation_id": "uuid"
    }

MCP tools return the same shape as JSON text (no HTTP status).

See docs/specification.md Error Handling section for the full table.
"""
from __future__ import annotations

import uuid

from fastapi import Request
from fastapi.responses import JSONResponse


class AgentError(Exception):
    """Base class for all domain errors in defi-agent.

    Subclasses set class-level `code` and `http_status`. Instances carry a
    human-readable `message`, an optional `suggestion`, and a `correlation_id`
    (auto-generated UUID unless provided).
    """

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        suggestion: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion
        self.correlation_id = correlation_id or str(uuid.uuid4())

    def to_dict(self) -> dict:
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "suggestion": self.suggestion,
            "correlation_id": self.correlation_id,
        }


# -- Auth ----------------------------------------------------------------


class AuthMissingApiKey(AgentError):
    code = "AUTH_MISSING_API_KEY"
    http_status = 401


class AuthInvalidApiKey(AgentError):
    code = "AUTH_INVALID_API_KEY"
    http_status = 401


# -- Validation / confirmation ------------------------------------------


class ValidationError(AgentError):
    code = "VALIDATION_ERROR"
    http_status = 400


class ConfirmationRequired(AgentError):
    code = "CONFIRMATION_REQUIRED"
    http_status = 400


# -- Wallet -------------------------------------------------------------


class WalletNotFound(AgentError):
    code = "WALLET_NOT_FOUND"
    http_status = 404


class WalletAlreadyExists(AgentError):
    code = "WALLET_ALREADY_EXISTS"
    http_status = 409


# -- Strategy -----------------------------------------------------------


class StrategyNotFound(AgentError):
    code = "STRATEGY_NOT_FOUND"
    http_status = 404


class StrategyInvalidStatusTransition(AgentError):
    code = "STRATEGY_INVALID_STATUS_TRANSITION"
    http_status = 400


class StrategyInvalidComposition(AgentError):
    code = "STRATEGY_INVALID_COMPOSITION"
    http_status = 400


class StrategyNoViableCandidates(AgentError):
    code = "STRATEGY_NO_VIABLE_CANDIDATES"
    http_status = 422


class AllocationInsufficient(AgentError):
    code = "ALLOCATION_INSUFFICIENT"
    http_status = 400


# -- External / internal -----------------------------------------------


class SdkError(AgentError):
    code = "SDK_ERROR"
    http_status = 502


class SigningError(AgentError):
    code = "SIGNING_ERROR"
    http_status = 500


class EvaluationError(AgentError):
    code = "EVALUATION_ERROR"
    http_status = 500


class SchedulerError(AgentError):
    code = "SCHEDULER_ERROR"
    http_status = 500


class ChainNotSupportedInV1(AgentError):
    code = "CHAIN_NOT_SUPPORTED_IN_V1"
    http_status = 501


class InternalError(AgentError):
    code = "INTERNAL_ERROR"
    http_status = 500


# -- FastAPI handler ---------------------------------------------------


async def agent_error_handler(request: Request, exc: AgentError) -> JSONResponse:
    """FastAPI exception handler for AgentError and subclasses.

    Returns the standard error response shape with the exception's http_status.
    Register via `app.add_exception_handler(AgentError, agent_error_handler)`.
    """
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_dict(),
    )
