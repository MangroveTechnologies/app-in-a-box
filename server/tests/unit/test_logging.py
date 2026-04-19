"""Unit tests for shared/logging.py — structured logging + correlation_id."""
from __future__ import annotations

import io
import json
import logging
import os
import sys
import uuid

os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402
import structlog  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.shared.logging import (  # noqa: E402
    CorrelationIdMiddleware,
    configure,
    get_logger,
    with_correlation_id,
)


@pytest.fixture
def capture_stderr(monkeypatch):
    """Redirect structlog's PrintLoggerFactory output to a buffer."""
    buf = io.StringIO()

    def factory(*_args, **_kwargs):
        from structlog import PrintLogger
        return PrintLogger(file=buf)

    monkeypatch.setattr(structlog, "PrintLoggerFactory", lambda *a, **kw: factory)
    yield buf


def _reconfigure(env: str, buf: io.StringIO) -> None:
    """Reconfigure structlog for the given env, writing to a test buffer."""
    from src.shared import logging as logmod

    # mirror configure() but redirect output
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.INFO, force=True)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        logmod._add_correlation_id,
    ]
    renderer = (
        structlog.dev.ConsoleRenderer(colors=False)
        if env == "local"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=buf),
        cache_logger_on_first_use=False,
    )


def test_console_renderer_in_local():
    buf = io.StringIO()
    _reconfigure("local", buf)
    get_logger().info("app.startup", version="0.1.0")
    out = buf.getvalue()
    assert "app.startup" in out
    assert "version" in out
    # Console renderer does NOT emit JSON
    assert not out.strip().startswith("{")


def test_json_renderer_in_prod():
    buf = io.StringIO()
    _reconfigure("prod", buf)
    get_logger().info("app.startup", version="0.1.0", foo="bar")
    out = buf.getvalue().strip()
    parsed = json.loads(out)
    assert parsed["event"] == "app.startup"
    assert parsed["version"] == "0.1.0"
    assert parsed["foo"] == "bar"
    assert parsed["level"] == "info"
    assert "timestamp" in parsed


def test_correlation_id_propagates_via_contextmanager():
    buf = io.StringIO()
    _reconfigure("prod", buf)
    cid = "abc-123"
    with with_correlation_id(cid):
        get_logger().info("strategy.tick.started", strategy_id="s1")
    out = buf.getvalue().strip()
    parsed = json.loads(out)
    assert parsed["correlation_id"] == cid


def test_correlation_id_absent_when_not_bound():
    buf = io.StringIO()
    _reconfigure("prod", buf)
    get_logger().info("something.else")
    parsed = json.loads(buf.getvalue().strip())
    assert "correlation_id" not in parsed


def test_middleware_echoes_header_when_supplied():
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    supplied = "caller-supplied-uuid"
    r = client.get("/ping", headers={"X-Correlation-Id": supplied})
    assert r.status_code == 200
    assert r.headers["x-correlation-id"] == supplied


def test_middleware_generates_header_when_missing():
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    r = client.get("/ping")
    assert r.status_code == 200
    cid = r.headers["x-correlation-id"]
    # Should be a parseable UUID
    uuid.UUID(cid)


def test_middleware_injects_id_into_request_scope_logs():
    """A log emitted during a request carries the request's correlation_id."""
    buf = io.StringIO()
    _reconfigure("prod", buf)

    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/tagged")
    async def tagged():
        get_logger().info("tagged.event", detail="x")
        return {"ok": True}

    client = TestClient(app)
    supplied = "fixed-cid-xyz"
    r = client.get("/tagged", headers={"X-Correlation-Id": supplied})
    assert r.status_code == 200

    # Parse the captured log line(s); find our tagged.event
    lines = [line for line in buf.getvalue().splitlines() if "tagged.event" in line]
    assert lines, "expected at least one log line for tagged.event"
    parsed = json.loads(lines[-1])
    assert parsed["correlation_id"] == supplied
    assert parsed["event"] == "tagged.event"


def test_configure_is_idempotent():
    # Calling twice should not raise.
    configure("test")
    configure("test")
