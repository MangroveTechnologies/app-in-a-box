"""Echo endpoint tests."""
import os
os.environ.setdefault("ENVIRONMENT", "test")


def test_echo_post(client):
    resp = client.post("/api/v1/echo", json={"hello": "world"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["echo"]["hello"] == "world"
    assert data["method"] == "POST"


def test_echo_get(client):
    resp = client.get("/api/v1/echo?foo=bar")
    assert resp.status_code == 200
    data = resp.json()
    assert data["echo"]["foo"] == "bar"
    assert data["method"] == "GET"
