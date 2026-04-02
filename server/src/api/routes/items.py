"""Items CRUD endpoints -- auth-gated (API key required).

Demonstrates the auth-gated access tier. All endpoints require a valid
API key in the X-API-Key header.
"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from src.services.items import create_item, delete_item, get_item, list_items
from src.shared.auth.middleware import validate_api_key

router = APIRouter()


class CreateItemRequest(BaseModel):
    """Request body for creating a new item."""
    name: str = Field(description="Item name")
    description: str = Field(default="", description="Optional item description")


class ItemResponse(BaseModel):
    """Single item response."""
    id: str = Field(description="Unique item ID (UUID)")
    name: str = Field(description="Item name")
    description: str = Field(description="Item description")
    created_at: str = Field(description="Creation timestamp (ISO 8601)")


class DeleteResponse(BaseModel):
    """Deletion confirmation."""
    deleted: bool = Field(description="True if item was deleted")


def _require_auth(x_api_key: str = None):
    try:
        validate_api_key(x_api_key)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post(
    "/items",
    status_code=201,
    response_model=ItemResponse,
    summary="Create item",
    description="Create a new item. Requires a valid API key in the X-API-Key header.",
    responses={401: {"description": "Missing or invalid API key"}},
)
async def create(body: CreateItemRequest, x_api_key: str = Header(None, alias="X-API-Key")):
    _require_auth(x_api_key)
    return create_item(body.name, body.description)


@router.get(
    "/items",
    response_model=list[ItemResponse],
    summary="List items",
    description="List all items. Requires a valid API key.",
    responses={401: {"description": "Missing or invalid API key"}},
)
async def list_all(x_api_key: str = Header(None, alias="X-API-Key")):
    _require_auth(x_api_key)
    return list_items()


@router.get(
    "/items/{item_id}",
    response_model=ItemResponse,
    summary="Get item by ID",
    description="Retrieve a single item by its UUID. Requires a valid API key.",
    responses={401: {"description": "Missing or invalid API key"}, 404: {"description": "Item not found"}},
)
async def get_by_id(item_id: str, x_api_key: str = Header(None, alias="X-API-Key")):
    _require_auth(x_api_key)
    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.delete(
    "/items/{item_id}",
    response_model=DeleteResponse,
    summary="Delete item",
    description="Delete an item by its UUID. Requires a valid API key.",
    responses={401: {"description": "Missing or invalid API key"}, 404: {"description": "Item not found"}},
)
async def remove(item_id: str, x_api_key: str = Header(None, alias="X-API-Key")):
    _require_auth(x_api_key)
    if not delete_item(item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    return {"deleted": True}
