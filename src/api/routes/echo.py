"""Echo endpoint -- free, no auth required.

Returns structured metadata about the request. Useful for agents
to verify connectivity and inspect response format.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter()


@router.post("/echo")
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


@router.get("/echo")
async def echo_get(request: Request):
    return {
        "echo": dict(request.query_params),
        "method": request.method,
        "path": str(request.url.path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
