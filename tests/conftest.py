"""Test configuration and fixtures."""
import os

os.environ["ENVIRONMENT"] = "test"

import pytest
from fastapi.testclient import TestClient

from src.app import app
from src.services.items import clear_items


@pytest.fixture
def client():
    clear_items()
    with TestClient(app) as c:
        yield c
    clear_items()
