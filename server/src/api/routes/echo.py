"""Echo endpoint -- free, no auth required.

Returns structured metadata about the request. Useful for agents
to verify connectivity and inspect response format.
"""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field


class EchoResponse(BaseModel):
    """Structured echo response with request metadata."""
    echo: Any = Field(description="Echoed request body or query parameters")
    method: str = Field(description="HTTP method used")
    path: str = Field(description="Request path")
    timestamp: str = Field(description="Server timestamp (ISO 8601)")


router = APIRouter()


@router.post(
    "/echo",
    response_model=EchoResponse,
    summary="Echo POST request",
    description="Echoes back the JSON request body along with request metadata. "
    "Free, no auth required. Useful for agents to verify connectivity.",
)
async def echo_post(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return {
        "echo": body,
        "method": request.method,
        "path": str(request.url.path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/echo",
    response_model=EchoResponse,
    summary="Echo GET request",
    description="Echoes back query parameters along with request metadata. "
    "Free, no auth required. Useful for agents to verify connectivity.",
)
async def echo_get(request: Request):
    return {
        "echo": dict(request.query_params),
        "method": request.method,
        "path": str(request.url.path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
