"""Test configuration and fixtures."""
import os

os.environ["ENVIRONMENT"] = "test"

import pytest
from fastapi.testclient import TestClient

from src.app import create_app


@pytest.fixture
def client():
    # Each test gets a fresh app + fresh MCP session manager. Sharing a
    # module-global app across tests breaks because FastMCP's session
    # manager's task group is closed after the first lifespan exit.
    app = create_app()
    with TestClient(app) as c:
        yield c
