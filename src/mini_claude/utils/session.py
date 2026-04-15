"""Session persistence using SQLite."""

import json
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime


class SessionManager:
    """Manage session persistence with SQLite."""

    def __init__(self, db_path: str = "sessions.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database."""
        conn = sqlite3.connect(self.db_path)
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

        conn.commit()
        conn.close()

    def save_session(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        summary: Optional[str] = None
    ) -> None:
        """Save or update a session."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        messages_json = json.dumps(messages, ensure_ascii=False)
        context_json = json.dumps(context, ensure_ascii=False) if context else None

        cursor.execute("""
            INSERT OR REPLACE INTO sessions (id, created_at, updated_at, messages, context, summary)
            VALUES (?, COALESCE((SELECT created_at FROM sessions WHERE id = ?), ?), ?, ?, ?, ?)
        """, (session_id, session_id, now, now, messages_json, context_json, summary))

        conn.commit()
        conn.close()

    def load_session(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """Load a session by ID (returns messages only for backward compatibility)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT messages FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return json.loads(row[0])
        return None

    def load_session_full(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load a session with all metadata."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, created_at, updated_at, messages, context, summary FROM sessions WHERE id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        conn.close()

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
        conn = sqlite3.connect(self.db_path)
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

        conn.close()
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()
        return deleted


# Global session manager
_session_manager: Optional[SessionManager] = None


def get_session_manager(db_path: str = "sessions.db") -> SessionManager:
    """Get or create the global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(db_path)
    return _session_manager
