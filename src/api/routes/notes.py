"""Notes CRUD -- PostgreSQL-backed, auth-gated.

Requires --profile full (PostgreSQL running) and DB keys in config.
Returns 503 if the database is not available.
"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.shared.auth.middleware import validate_api_key

router = APIRouter(prefix="/notes", tags=["notes"])


_DB_503 = "Database not available. Start with --profile full and configure DB keys."


def _require_auth(api_key: Optional[str]):
    try:
        validate_api_key(api_key)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


def _is_db_error(e: Exception) -> bool:
    msg = str(e).lower()
    return any(kw in msg for kw in ["database", "connect", "db_host", "_config"])


class NoteCreate(BaseModel):
    title: str
    content: str = ""


@router.post("", status_code=201)
def create_note(body: NoteCreate, x_api_key: Optional[str] = Header(None)):
    _require_auth(x_api_key)
    try:
        from src.services.notes import create_note as _create
        return _create(body.title, body.content)
    except HTTPException:
        raise
    except Exception as e:
        if _is_db_error(e):
            raise HTTPException(status_code=503, detail=_DB_503)
        raise


@router.get("")
def list_notes(x_api_key: Optional[str] = Header(None)):
    _require_auth(x_api_key)
    try:
        from src.services.notes import list_notes as _list
        return _list()
    except Exception as e:
        if _is_db_error(e):
            raise HTTPException(status_code=503, detail=_DB_503)
        raise


@router.get("/{note_id}")
def get_note(note_id: str, x_api_key: Optional[str] = Header(None)):
    _require_auth(x_api_key)
    try:
        from src.services.notes import get_note as _get
        result = _get(note_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        if _is_db_error(e):
            raise HTTPException(status_code=503, detail=_DB_503)
        raise


@router.delete("/{note_id}")
def delete_note(note_id: str, x_api_key: Optional[str] = Header(None)):
    _require_auth(x_api_key)
    try:
        from src.services.notes import delete_note as _delete
        if not _delete(note_id):
            raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        if _is_db_error(e):
            raise HTTPException(status_code=503, detail=_DB_503)
        raise
