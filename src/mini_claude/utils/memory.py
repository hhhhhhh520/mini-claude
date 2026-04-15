"""Session memory and persistence utilities.

DEPRECATED: This module is deprecated. Use SessionManager from session.py instead.
The SessionManager provides better SQLite-based persistence with enhanced features.
"""

import warnings

# Show deprecation warning when this module is imported
warnings.warn(
    "memory.py is deprecated. Use SessionManager from session.py instead.",
    DeprecationWarning,
    stacklevel=2
)

import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field, asdict


@dataclass
class SessionMemory:
    """Memory for a conversation session."""
    thread_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    messages: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    summary: Optional[str] = None

    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        """Add a message to memory."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        })
        self.updated_at = datetime.now().isoformat()

    def get_recent_messages(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get the n most recent messages."""
        return self.messages[-n:]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class MemoryManager:
    """Manages session memories."""

    def __init__(self, storage_dir: str = ".mini_claude_memory"):
        self.storage_dir = storage_dir
        self.sessions: Dict[str, SessionMemory] = {}
        os.makedirs(storage_dir, exist_ok=True)

    def get_session(self, thread_id: str) -> SessionMemory:
        """Get or create a session."""
        if thread_id not in self.sessions:
            # Try to load from disk
            filepath = os.path.join(self.storage_dir, f"{thread_id}.json")
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.sessions[thread_id] = SessionMemory(**data)
                except Exception:
                    self.sessions[thread_id] = SessionMemory(thread_id=thread_id)
            else:
                self.sessions[thread_id] = SessionMemory(thread_id=thread_id)

        return self.sessions[thread_id]

    def save_session(self, thread_id: str):
        """Save a session to disk."""
        if thread_id not in self.sessions:
            return

        filepath = os.path.join(self.storage_dir, f"{thread_id}.json")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.sessions[thread_id].to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving session: {e}")

    def list_sessions(self) -> List[str]:
        """List all session IDs."""
        sessions = set(self.sessions.keys())
        for filename in os.listdir(self.storage_dir):
            if filename.endswith(".json"):
                sessions.add(filename[:-5])
        return sorted(sessions)

    def delete_session(self, thread_id: str):
        """Delete a session."""
        if thread_id in self.sessions:
            del self.sessions[thread_id]

        filepath = os.path.join(self.storage_dir, f"{thread_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)

    def clear_all(self):
        """Clear all sessions."""
        self.sessions.clear()
        for filename in os.listdir(self.storage_dir):
            if filename.endswith(".json"):
                os.remove(os.path.join(self.storage_dir, filename))


# Global memory manager
memory_manager = MemoryManager()
