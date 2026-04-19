"""Test configuration and fixtures."""
import os

os.environ["ENVIRONMENT"] = "test"

import pytest
from fastapi.testclient import TestClient

from src.app import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
