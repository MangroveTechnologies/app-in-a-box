"""Items CRUD endpoints -- auth-gated (API key required).

Demonstrates the auth-gated access tier.
"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.shared.auth.middleware import validate_api_key
from src.services.items import create_item, get_item, list_items, delete_item

router = APIRouter()


class CreateItemRequest(BaseModel):
    name: str
    description: str = ""


def _require_auth(x_api_key: str = None):
    try:
        validate_api_key(x_api_key)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/items", status_code=201)
async def create(body: CreateItemRequest, x_api_key: str = Header(None, alias="X-API-Key")):
    _require_auth(x_api_key)
    return create_item(body.name, body.description)


@router.get("/items")
async def list_all(x_api_key: str = Header(None, alias="X-API-Key")):
    _require_auth(x_api_key)
    return list_items()


@router.get("/items/{item_id}")
async def get_by_id(item_id: str, x_api_key: str = Header(None, alias="X-API-Key")):
    _require_auth(x_api_key)
    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.delete("/items/{item_id}")
async def remove(item_id: str, x_api_key: str = Header(None, alias="X-API-Key")):
    _require_auth(x_api_key)
    if not delete_item(item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    return {"deleted": True}
