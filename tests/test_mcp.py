"""MCP server registration tests."""
import os
os.environ.setdefault("ENVIRONMENT", "test")

from src.mcp.server import create_mcp_server


def test_mcp_server_creates_successfully():
    server = create_mcp_server()
    assert server.name == "gcp-app-template"


def test_mcp_server_has_expected_name():
    server = create_mcp_server()
    assert server is not None
