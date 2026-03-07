"""FastAPI application factory.

Serves dual protocols:
- REST API at /api/v1/*
- MCP server at /mcp (mounted in lifespan, added in Task 9)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.health import health_payload
from src.api.router import api_router


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Mount MCP server
    from src.mcp.server import create_mcp_server
    mcp_server = create_mcp_server()
    application.mount("/mcp", mcp_server.http_app())
    yield


app = FastAPI(
    title="GCP App Template",
    description="FastAPI + MCP service template with three-tier access control",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return health_payload()
