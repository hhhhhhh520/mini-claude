"""Session persistence using SQLite."""

import json
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import contextmanager


class SessionManager:
    """Manage session persistence with SQLite."""

    def __init__(self, db_path: str = "sessions.db"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Get database connection with context manager."""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    context TEXT,
                    summary TEXT
                )
            """)

    def save_session(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        summary: Optional[str] = None
    ) -> None:
        """Save or update a session."""
        now = datetime.now().isoformat()
        messages_json = json.dumps(messages, ensure_ascii=False)
        context_json = json.dumps(context, ensure_ascii=False) if context else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO sessions (id, created_at, updated_at, messages, context, summary)
                VALUES (?, COALESCE((SELECT created_at FROM sessions WHERE id = ?), ?), ?, ?, ?, ?)
            """, (session_id, session_id, now, now, messages_json, context_json, summary))

    def load_session(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """Load a session by ID (returns messages only for backward compatibility)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT messages FROM sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()

        if row:
            return json.loads(row[0])
        return None

    def load_session_full(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load a session with all metadata."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, created_at, updated_at, messages, context, summary FROM sessions WHERE id = ?",
                (session_id,)
            )
            row = cursor.fetchone()

        if row:
            return {
                "id": row[0],
                "created_at": row[1],
                "updated_at": row[2],
                "messages": json.loads(row[3]),
                "context": json.loads(row[4]) if row[4] else None,
                "summary": row[5],
            }
        return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, created_at, updated_at,
                       json_array_length(messages) as msg_count
                FROM sessions
                ORDER BY updated_at DESC
            """)

            sessions = []
            for row in cursor.fetchall():
                sessions.append({
                    "id": row[0],
                    "created_at": row[1],
                    "updated_at": row[2],
                    "message_count": row[3],
                })

        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            deleted = cursor.rowcount > 0

        return deleted


# Global session manager
_session_manager: Optional[SessionManager] = None


def get_session_manager(db_path: str = "sessions.db") -> SessionManager:
    """Get or create the global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(db_path)
    return _session_manager
