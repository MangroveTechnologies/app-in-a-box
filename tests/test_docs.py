"""Auto-documentation endpoint tests."""
import os
os.environ.setdefault("ENVIRONMENT", "test")


def test_tool_catalog_returns_all_tools(client):
    resp = client.get("/api/v1/docs/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert "tools" in data
    assert "total" in data
    assert data["total"] == 5

    names = {t["name"] for t in data["tools"]}
    assert names == {"echo", "items_create", "items_list", "items_get", "easter_egg"}


def test_tool_catalog_includes_access_tiers(client):
    resp = client.get("/api/v1/docs/tools")
    tools = {t["name"]: t for t in resp.json()["tools"]}

    assert tools["echo"]["access"] == "free"
    assert tools["items_create"]["access"] == "auth"
    assert tools["easter_egg"]["access"] == "x402"


def test_tool_catalog_includes_x402_pricing(client):
    resp = client.get("/api/v1/docs/tools")
    tools = {t["name"]: t for t in resp.json()["tools"]}

    assert tools["easter_egg"]["price"] == "$0.05 USDC"
    assert tools["easter_egg"]["network"] == "base"
    assert "price" not in tools["echo"]


def test_tool_catalog_includes_parameters(client):
    resp = client.get("/api/v1/docs/tools")
    tools = {t["name"]: t for t in resp.json()["tools"]}

    echo_params = tools["echo"]["parameters"]
    assert len(echo_params) == 1
    assert echo_params[0]["name"] == "message"
    assert echo_params[0]["required"] is False

    create_params = tools["items_create"]["parameters"]
    assert len(create_params) == 2
    assert any(p["name"] == "name" and p["required"] is True for p in create_params)


def test_openapi_spec_available(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "x402 App Template"


def test_swagger_ui_available(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
