"""MCP tool registry with access tier metadata.

Maintains a catalog of all registered MCP tools with their access tier,
parameters, and pricing info. Used by the /api/v1/docs/tools discovery
endpoint so agents can programmatically discover what tools exist and
what each one costs before connecting via MCP.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolParam:
    name: str
    type: str
    required: bool
    description: str = ""


@dataclass
class ToolEntry:
    name: str
    description: str
    access: str  # "free", "auth", "x402"
    parameters: list[ToolParam] = field(default_factory=list)
    price: Optional[str] = None  # e.g. "$0.05 USDC"
    network: Optional[str] = None  # e.g. "base"


_tools: list[ToolEntry] = []


def register_tool(entry: ToolEntry):
    """Register a tool in the discovery catalog."""
    _tools.append(entry)


def list_tools() -> list[dict]:
    """Return all registered tools as dicts for JSON serialization."""
    result = []
    for t in _tools:
        entry = {
            "name": t.name,
            "description": t.description,
            "access": t.access,
            "parameters": [
                {"name": p.name, "type": p.type, "required": p.required, "description": p.description}
                for p in t.parameters
            ],
        }
        if t.price:
            entry["price"] = t.price
        if t.network:
            entry["network"] = t.network
        result.append(entry)
    return result


def clear_tools():
    """Clear registry. Used in tests."""
    _tools.clear()
