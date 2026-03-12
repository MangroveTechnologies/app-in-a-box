"""Notes service -- PostgreSQL-backed CRUD.

Demonstrates the full DB pattern: config -> pool -> query -> response.
Requires --profile full (PostgreSQL running) and DB keys in config.
"""
from src.shared.db.pool import DatabaseUtils


def create_note(title: str, content: str = "") -> dict:
    conn = DatabaseUtils.db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO notes (title, content) VALUES (%s, %s) RETURNING id, title, content, created_at",
                (title, content),
            )
            row = cur.fetchone()
            conn.commit()
            return {
                "id": str(row[0]),
                "title": row[1],
                "content": row[2],
                "created_at": row[3].isoformat(),
            }
    finally:
        conn.close()


def get_note(note_id: str) -> dict | None:
    conn = DatabaseUtils.db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, content, created_at FROM notes WHERE id = %s",
                (note_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": str(row[0]),
                "title": row[1],
                "content": row[2],
                "created_at": row[3].isoformat(),
            }
    finally:
        conn.close()


def list_notes() -> list[dict]:
    conn = DatabaseUtils.db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, content, created_at FROM notes ORDER BY created_at DESC")
            return [
                {
                    "id": str(row[0]),
                    "title": row[1],
                    "content": row[2],
                    "created_at": row[3].isoformat(),
                }
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def delete_note(note_id: str) -> bool:
    conn = DatabaseUtils.db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notes WHERE id = %s", (note_id,))
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted
    finally:
        conn.close()
