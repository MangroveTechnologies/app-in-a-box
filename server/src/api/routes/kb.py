"""Knowledge Base routes — pass-through to mangroveai.kb."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src.shared.auth.dependency import require_api_key
from src.shared.clients.mangrove import mangroveai_client
from src.shared.errors import SdkError

router = APIRouter(
    prefix="/kb",
    dependencies=[Depends(require_api_key)],
    tags=["kb"],
)


def _dump(obj: Any) -> Any:
    return obj.model_dump() if hasattr(obj, "model_dump") else obj


@router.get("/search", summary="Full-text search the knowledge base")
async def search(q: str, limit: int = 20) -> Any:
    try:
        return _dump(mangroveai_client().kb.search.query(q=q, limit=limit))
    except Exception as e:  # noqa: BLE001
        raise SdkError(f"kb.search.query failed: {e}") from e


@router.get("/glossary/{term}", summary="Glossary term lookup with backlinks")
async def glossary(term: str) -> Any:
    try:
        return _dump(mangroveai_client().kb.glossary.get(term))
    except Exception as e:  # noqa: BLE001
        raise SdkError(f"kb.glossary.get failed: {e}") from e
