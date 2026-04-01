"""Notes endpoint tests (PostgreSQL-backed, DB mocked)."""
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENVIRONMENT", "test")


def _mock_note(note_id="abc-123", title="Test", content="Hello"):
    return {
        "id": note_id,
        "title": title,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def test_create_note_without_auth_returns_401(client):
    resp = client.post("/api/v1/notes", json={"title": "test"})
    assert resp.status_code == 401


@patch("src.services.notes.DatabaseUtils.db_connect")
def test_create_note_with_auth(mock_connect, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (
        "abc-123", "My Note", "content", datetime.now(timezone.utc),
    )
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value = mock_conn

    resp = client.post(
        "/api/v1/notes",
        json={"title": "My Note", "content": "content"},
        headers={"X-API-Key": "test-key-1"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "My Note"
    assert data["id"] == "abc-123"


@patch("src.services.notes.DatabaseUtils.db_connect")
def test_list_notes_with_auth(mock_connect, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        ("id-1", "Note 1", "c1", datetime.now(timezone.utc)),
        ("id-2", "Note 2", "c2", datetime.now(timezone.utc)),
    ]
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value = mock_conn

    resp = client.get("/api/v1/notes", headers={"X-API-Key": "test-key-1"})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@patch("src.services.notes.DatabaseUtils.db_connect")
def test_get_note_not_found(mock_connect, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value = mock_conn

    resp = client.get("/api/v1/notes/missing-id", headers={"X-API-Key": "test-key-1"})
    assert resp.status_code == 404


def test_notes_returns_503_without_db(client):
    resp = client.get("/api/v1/notes", headers={"X-API-Key": "test-key-1"})
    assert resp.status_code == 503
    assert "Database not available" in resp.json()["detail"]
