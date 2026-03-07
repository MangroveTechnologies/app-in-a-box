"""Items service -- in-memory CRUD for demo purposes.

Replace with PostgreSQL queries for production use.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional


_items: dict[str, dict] = {}


def create_item(name: str, description: str = "") -> dict:
    item_id = str(uuid.uuid4())
    item = {
        "id": item_id,
        "name": name,
        "description": description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _items[item_id] = item
    return item


def get_item(item_id: str) -> Optional[dict]:
    return _items.get(item_id)


def list_items() -> list[dict]:
    return list(_items.values())


def delete_item(item_id: str) -> bool:
    return _items.pop(item_id, None) is not None


def clear_items():
    """Clear all items. Used in tests."""
    _items.clear()
