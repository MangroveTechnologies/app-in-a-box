"""Test configuration and fixtures."""
import os
os.environ["ENVIRONMENT"] = "test"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    # Force reimport to pick up test environment
    import importlib
    import src.app
    importlib.reload(src.app)
    return TestClient(src.app.app)
