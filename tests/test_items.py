"""Items CRUD endpoint tests (auth-gated)."""
import os
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from src.services.items import clear_items


@pytest.fixture(autouse=True)
def _clean_items():
    clear_items()
    yield
    clear_items()


def test_create_item_without_auth_returns_401(client):
    resp = client.post("/api/v1/items", json={"name": "Widget", "description": "A widget"})
    assert resp.status_code == 401


def test_create_item_with_valid_key(client):
    resp = client.post(
        "/api/v1/items",
        json={"name": "Widget", "description": "A widget"},
        headers={"X-API-Key": "test-key-1"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Widget"
    assert "id" in data


def test_list_items_with_valid_key(client):
    client.post("/api/v1/items", json={"name": "Gadget"}, headers={"X-API-Key": "test-key-1"})
    resp = client.get("/api/v1/items", headers={"X-API-Key": "test-key-1"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


def test_get_item_by_id(client):
    create_resp = client.post(
        "/api/v1/items",
        json={"name": "Thing", "description": "A thing"},
        headers={"X-API-Key": "test-key-1"},
    )
    item_id = create_resp.json()["id"]
    resp = client.get(f"/api/v1/items/{item_id}", headers={"X-API-Key": "test-key-1"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Thing"


def test_get_nonexistent_item_returns_404(client):
    resp = client.get("/api/v1/items/nonexistent-id", headers={"X-API-Key": "test-key-1"})
    assert resp.status_code == 404


def test_delete_item(client):
    create_resp = client.post(
        "/api/v1/items", json={"name": "Temp"}, headers={"X-API-Key": "test-key-1"},
    )
    item_id = create_resp.json()["id"]
    resp = client.delete(f"/api/v1/items/{item_id}", headers={"X-API-Key": "test-key-1"})
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
