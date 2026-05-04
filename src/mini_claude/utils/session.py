"""Session persistence using SQLite."""

import json
import sqlite3
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import contextmanager

from ..agent.state import ExecutionState


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
                    summary TEXT,
                    token_count INTEGER DEFAULT 0,
                    compressed_at TEXT,
                    execution_state TEXT
                )
            """)
            # Add new columns to existing tables
            try:
                cursor.execute("ALTER TABLE sessions ADD COLUMN token_count INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute("ALTER TABLE sessions ADD COLUMN compressed_at TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute("ALTER TABLE sessions ADD COLUMN execution_state TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

    def save_session(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        summary: Optional[str] = None,
        token_count: int = 0,
    ) -> None:
        """Save or update a session, preserving execution_state if exists."""
        now = datetime.now().isoformat()
        messages_json = json.dumps(messages, ensure_ascii=False)
        context_json = json.dumps(context, ensure_ascii=False) if context else None
        compressed_at = now if summary else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Use UPDATE if session exists to preserve execution_state
            cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
            if cursor.fetchone():
                cursor.execute("""
                    UPDATE sessions SET
                    updated_at = ?, messages = ?, context = ?, summary = ?, token_count = ?, compressed_at = ?
                    WHERE id = ?
                """, (now, messages_json, context_json, summary, token_count, compressed_at, session_id))
            else:
                # INSERT new session without execution_state
                cursor.execute("""
                    INSERT INTO sessions
                    (id, created_at, updated_at, messages, context, summary, token_count, compressed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (session_id, now, now, messages_json, context_json, summary, token_count, compressed_at))

    def load_session(self, session_id: str) -> tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """Load a session by ID.

        Returns:
            Tuple of (messages, summary) for backward compatibility.
            If session not found, returns (None, None).
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT messages, summary FROM sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()

        if row:
            return json.loads(row[0]), row[1]
        return None, None

    def load_session_full(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load a session with all metadata."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, created_at, updated_at, messages, context, summary, token_count, compressed_at FROM sessions WHERE id = ?",
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
                "token_count": row[6] or 0,
                "compressed_at": row[7],
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

    # ========== Execution State Methods (断点续跑) ==========

    def save_execution_state(
        self,
        session_id: str,
        state: ExecutionState,
    ) -> bool:
        """Save execution state for a session.

        Args:
            session_id: Session identifier
            state: ExecutionState to save

        Returns:
            True if saved successfully
        """
        state.update_timestamp()
        state_json = json.dumps(state.to_dict(), ensure_ascii=False)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Check if session exists
            cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE sessions SET execution_state = ?, updated_at = ? WHERE id = ?",
                    (state_json, datetime.now().isoformat(), session_id)
                )
            else:
                # Create a new session with execution state
                now = datetime.now().isoformat()
                cursor.execute(
                    """INSERT INTO sessions
                    (id, created_at, updated_at, messages, execution_state)
                    VALUES (?, ?, ?, '[]', ?)""",
                    (session_id, now, now, state_json)
                )
        return True

    def load_execution_state(self, session_id: str) -> Optional[ExecutionState]:
        """Load execution state for a session.

        Args:
            session_id: Session identifier

        Returns:
            ExecutionState if found and valid, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT execution_state FROM sessions WHERE id = ?",
                (session_id,)
            )
            row = cursor.fetchone()

        if row and row[0]:
            try:
                data = json.loads(row[0])
                state = ExecutionState.from_dict(data)
                if state.is_valid():
                    return state
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        return None

    def clear_execution_state(self, session_id: str) -> bool:
        """Clear execution state for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if cleared successfully
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sessions SET execution_state = NULL, updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), session_id)
            )
        return True

    def list_interrupted_sessions(self) -> List[Dict[str, Any]]:
        """List sessions with valid execution state (interrupted sessions).

        Returns:
            List of interrupted sessions with their execution state summary
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, created_at, updated_at, execution_state
                FROM sessions
                WHERE execution_state IS NOT NULL AND execution_state != ''
                ORDER BY updated_at DESC
            """)
            rows = cursor.fetchall()

        interrupted = []
        for row in rows:
            try:
                state_data = json.loads(row[3])
                state = ExecutionState.from_dict(state_data)
                if state.is_valid():
                    interrupted.append({
                        "id": row[0],
                        "created_at": row[1],
                        "updated_at": row[2],
                        "current_node": state.current_node,
                        "iteration_count": state.iteration_count,
                        "has_error": bool(state.last_error),
                    })
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        return interrupted


# Global session manager
_session_manager: Optional[SessionManager] = None


def get_session_manager(db_path: str = "sessions.db") -> SessionManager:
    """Get or create the global session manager.

    This function provides backward compatibility with existing code.
    New code should prefer ApplicationContext.session_manager.

    Args:
        db_path: Path to the session database file.

    Returns:
        Singleton SessionManager instance.
    """
    global _session_manager
    if _session_manager is None:
        # Try to use ApplicationContext first
        try:
            from mini_claude.context import get_context
            ctx = get_context()
            if ctx._session_manager.is_initialized():
                _session_manager = ctx.session_manager
            else:
                _session_manager = SessionManager(db_path)
                ctx.session_manager = _session_manager
        except ImportError:
            _session_manager = SessionManager(db_path)
    return _session_manager


def reset_session_manager() -> None:
    """Reset the global session manager (for testing)."""
    global _session_manager
    _session_manager = None
    # Also reset in context
    try:
        from mini_claude.context import get_context
        ctx = get_context()
        ctx._session_manager.reset()
    except ImportError:
        pass
