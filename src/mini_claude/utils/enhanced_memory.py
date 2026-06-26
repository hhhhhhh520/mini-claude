"""Enhanced memory manager with semantic search capabilities.

Integrates VectorStore for semantic search and SessionManager for
cross-session history retrieval.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .session import SessionManager
from .vector_store import (
    VectorStore,
    DependencyNotFoundError,
    check_vector_store_dependencies,
    get_recommended_backend,
)

logger = logging.getLogger(__name__)


@dataclass
class SessionSearchResult:
    """A search result with session context.

    Attributes:
        session_id: ID of the session containing the message
        message_idx: Index of the message in the session
        role: Role of the message (user/assistant/system)
        content: The message content
        score: Similarity score
        timestamp: When the session was created/updated
        session_type: Optional session type metadata
    """

    session_id: str
    message_idx: int
    role: str
    content: str
    score: float
    timestamp: Optional[str] = None
    session_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "session_id": self.session_id,
            "message_idx": self.message_idx,
            "role": self.role,
            "content": self.content,
            "score": self.score,
            "timestamp": self.timestamp,
            "session_type": self.session_type,
        }


class EnhancedMemoryManager:
    """Memory manager with semantic search across sessions.

    This class integrates:
    - SessionManager: For session persistence
    - VectorStore: For semantic search

    Example:
        >>> manager = EnhancedMemoryManager()
        >>> manager.index_session("session-123")
        >>> results = manager.search_history("how to deploy", k=5)
        >>> context = manager.get_relevant_context("previous errors", max_tokens=1000)
    """

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        session_manager: Optional[SessionManager] = None,
        vector_store_path: str = "~/.mini_claude/vectors",
        session_db_path: str = "sessions.db",
        collection_name: str = "conversation_memory",
        auto_index: bool = True,
    ):
        """Initialize the enhanced memory manager.

        Args:
            vector_store: Optional pre-configured VectorStore instance
            session_manager: Optional pre-configured SessionManager instance
            vector_store_path: Path for vector store persistence
            session_db_path: Path for session database
            collection_name: Name of the vector store collection
            auto_index: Whether to automatically index new sessions

        Raises:
            DependencyNotFoundError: If vector store dependencies are not available
        """
        self.auto_index = auto_index
        self._indexed_sessions: set = set()  # Track indexed session IDs

        # Initialize session manager
        if session_manager is not None:
            self._session_manager = session_manager
        else:
            self._session_manager = SessionManager(session_db_path)

        # Initialize vector store
        if vector_store is not None:
            self._vector_store = vector_store
        else:
            # Check dependencies before creating
            deps = check_vector_store_dependencies()
            if not deps.get("sentence_transformers", False):
                raise DependencyNotFoundError(
                    "sentence-transformers is required for semantic search. "
                    "Install it with: pip install sentence-transformers"
                )

            try:
                backend = get_recommended_backend()
            except DependencyNotFoundError:
                raise DependencyNotFoundError(
                    "No vector store backend available. "
                    "Install chromadb or faiss-cpu: "
                    "pip install chromadb OR pip install faiss-cpu numpy"
                )

            self._vector_store = VectorStore(
                db_type=backend,
                path=vector_store_path,
                collection_name=collection_name,
            )

        # Load previously indexed sessions
        self._load_indexed_sessions()

    def _load_indexed_sessions(self) -> None:
        """Load the set of already indexed sessions from vector store."""
        try:
            if hasattr(self.vector_store, "_documents"):
                for doc_id in self.vector_store._documents:
                    # Extract session_id from message_id format "session_id:message_idx"
                    session_id = self._parse_message_id(doc_id)[0]
                    self._indexed_sessions.add(session_id)
        except Exception:
            pass  # First run or empty store is normal

    def _generate_message_id(self, session_id: str, message_idx: int) -> str:
        """Generate a unique ID for a message.

        Args:
            session_id: Session identifier
            message_idx: Message index in the session

        Returns:
            Unique identifier for the message
        """
        return f"{session_id}:{message_idx}"

    def _parse_message_id(self, message_id: str) -> Tuple[str, int]:
        """Parse a message ID into session_id and message_idx.

        Args:
            message_id: Message identifier in format "session_id:message_idx"

        Returns:
            Tuple of (session_id, message_idx)
        """
        parts = message_id.rsplit(":", 1)
        if len(parts) == 2:
            return parts[0], int(parts[1])
        return message_id, 0

    def index_session(self, session_id: str) -> bool:
        """Index a session's messages into the vector store.

        Args:
            session_id: ID of the session to index

        Returns:
            True if indexing was successful, False if session not found
        """
        session_data = self._session_manager.load_session_full(session_id)
        if not session_data:
            logger.warning(f"Session not found: {session_id}")
            return False

        messages = session_data.get("messages", [])
        if not messages:
            logger.debug(f"Session has no messages: {session_id}")
            return True  # Empty session is not an error

        # Prepare batch data for vector store
        ids = []
        texts = []
        metadatas = []

        for idx, message in enumerate(messages):
            content = message.get("content", "")
            role = message.get("role", "unknown")
            timestamp = message.get("timestamp")

            # Skip empty messages
            if not content or not content.strip():
                continue

            # Skip system messages (usually not useful for search)
            if role == "system":
                continue

            message_id = self._generate_message_id(session_id, idx)
            ids.append(message_id)
            texts.append(content)

            # Build metadata
            metadata = {
                "session_id": session_id,
                "message_idx": idx,
                "role": role,
                "session_created_at": session_data.get("created_at"),
                "session_updated_at": session_data.get("updated_at"),
            }
            if timestamp:
                metadata["timestamp"] = timestamp

            metadatas.append(metadata)

        if not ids:
            logger.debug(f"No messages to index for session: {session_id}")
            return True

        try:
            self._vector_store.add_batch(ids, texts, metadatas)
            self._indexed_sessions.add(session_id)
            logger.info(f"Indexed {len(ids)} messages from session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to index session {session_id}: {e}")
            return False

    def index_all_sessions(self) -> int:
        """Index all sessions into the vector store.

        Returns:
            Number of sessions successfully indexed
        """
        sessions = self._session_manager.list_sessions()
        indexed_count = 0

        for session_info in sessions:
            session_id = session_info["id"]
            if session_id not in self._indexed_sessions:
                if self.index_session(session_id):
                    indexed_count += 1

        logger.info(f"Indexed {indexed_count} sessions")
        return indexed_count

    def search_history(
        self,
        query: str,
        k: int = 5,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        session_type: Optional[str] = None,
        role_filter: Optional[str] = None,
    ) -> List[SessionSearchResult]:
        """Search for similar content across all indexed sessions.

        Args:
            query: Search query text
            k: Maximum number of results to return
            time_range: Optional tuple of (start_time, end_time) to filter results
            session_type: Optional session type to filter results
            role_filter: Optional role filter (user/assistant)

        Returns:
            List of SessionSearchResult objects sorted by similarity
        """
        try:
            # Build metadata filter for ChromaDB
            metadata_filter = None
            if role_filter:
                metadata_filter = {"role": role_filter}

            # Search vector store
            results = self._vector_store.search_similar(
                query,
                k=k * 2,  # Get more results for post-filtering
                filter=metadata_filter,
            )
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

        # Convert and filter results
        search_results = []
        for result in results:
            session_id = result.metadata.get("session_id", "")
            message_idx = result.metadata.get("message_idx", 0)

            # Apply time range filter
            if time_range:
                timestamp_str = result.metadata.get("timestamp") or result.metadata.get(
                    "session_updated_at"
                )
                if timestamp_str:
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str)
                        start_time, end_time = time_range
                        if not (start_time <= timestamp <= end_time):
                            continue
                    except (ValueError, TypeError):
                        pass

            # Apply session type filter (if metadata exists)
            if session_type:
                result_session_type = result.metadata.get("session_type")
                if result_session_type != session_type:
                    continue

            search_results.append(
                SessionSearchResult(
                    session_id=session_id,
                    message_idx=message_idx,
                    role=result.metadata.get("role", "unknown"),
                    content=result.text,
                    score=result.score,
                    timestamp=result.metadata.get("timestamp")
                    or result.metadata.get("session_updated_at"),
                    session_type=result.metadata.get("session_type"),
                )
            )

            # Stop when we have enough results
            if len(search_results) >= k:
                break

        return search_results

    def get_relevant_context(
        self,
        query: str,
        max_tokens: int = 2000,
        include_sessions: Optional[List[str]] = None,
    ) -> List[str]:
        """Get relevant historical context for a query.

        This method retrieves similar messages from history and formats them
        for injection into the current conversation context.

        Args:
            query: Current query to find relevant context for
            max_tokens: Maximum total tokens for the context (approximate)
            include_sessions: Optional list of specific sessions to search

        Returns:
            List of formatted context strings
        """
        # Estimate tokens per character (rough approximation)
        # Average: ~4 characters per token for English
        chars_per_token = 4
        max_chars = max_tokens * chars_per_token

        # Build session filter if specified
        if include_sessions:
            # For now, we'll filter after retrieval
            # A more sophisticated approach would modify the vector store query
            pass

        # Search for relevant messages
        try:
            results = self._vector_store.search_similar(query, k=10)
        except Exception as e:
            logger.error(f"Context search failed: {e}")
            return []

        # Format results as context
        context_strings = []
        total_chars = 0

        for result in results:
            # Skip if session is in exclude list
            if include_sessions:
                session_id = result.metadata.get("session_id", "")
                if session_id not in include_sessions:
                    continue

            role = result.metadata.get("role", "unknown")
            content = result.text
            session_id = result.metadata.get("session_id", "unknown")

            # Format as context string
            context_str = f"[{session_id}] {role}: {content}"

            # Check token budget
            if total_chars + len(context_str) > max_chars:
                break

            context_strings.append(context_str)
            total_chars += len(context_str)

        return context_strings

    def get_session_messages(
        self,
        session_id: str,
        start_idx: int = 0,
        end_idx: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get messages from a specific session.

        Args:
            session_id: Session identifier
            start_idx: Starting message index
            end_idx: Ending message index (exclusive)

        Returns:
            List of message dictionaries
        """
        session_data = self._session_manager.load_session_full(session_id)
        if not session_data:
            return []

        messages = session_data.get("messages", [])
        if end_idx is not None:
            return messages[start_idx:end_idx]
        return messages[start_idx:]

    def delete_session_index(self, session_id: str) -> bool:
        """Remove a session's messages from the vector store.

        Args:
            session_id: ID of the session to remove

        Returns:
            True if any messages were removed
        """
        session_data = self._session_manager.load_session_full(session_id)
        if not session_data:
            return False

        messages = session_data.get("messages", [])
        removed = False

        for idx, message in enumerate(messages):
            content = message.get("content", "")
            if not content or not content.strip():
                continue

            message_id = self._generate_message_id(session_id, idx)
            try:
                if self._vector_store.delete_by_id(message_id):
                    removed = True
            except Exception as e:
                logger.warning(f"Failed to delete message {message_id}: {e}")

        if session_id in self._indexed_sessions:
            self._indexed_sessions.remove(session_id)

        return removed

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the memory manager.

        Returns:
            Dictionary with statistics
        """
        session_count = len(self._session_manager.list_sessions())

        return {
            "total_sessions": session_count,
            "indexed_sessions": len(self._indexed_sessions),
            "vector_store_stats": self._vector_store.get_stats(),
        }

    def clear(self) -> bool:
        """Clear all indexed data from the vector store.

        Returns:
            True if successful
        """
        try:
            self._vector_store.clear()
            self._indexed_sessions.clear()
            logger.info("Cleared all indexed data")
            return True
        except Exception as e:
            logger.error(f"Failed to clear vector store: {e}")
            return False


# Global instance for convenience
_enhanced_memory_manager: Optional[EnhancedMemoryManager] = None


def get_enhanced_memory_manager(
    vector_store_path: str = "~/.mini_claude/vectors",
    session_db_path: str = "sessions.db",
) -> EnhancedMemoryManager:
    """Get or create the global enhanced memory manager.

    Args:
        vector_store_path: Path for vector store persistence
        session_db_path: Path for session database

    Returns:
        EnhancedMemoryManager instance
    """
    global _enhanced_memory_manager
    if _enhanced_memory_manager is None:
        try:
            _enhanced_memory_manager = EnhancedMemoryManager(
                vector_store_path=vector_store_path,
                session_db_path=session_db_path,
            )
        except DependencyNotFoundError as e:
            logger.warning(f"Enhanced memory manager unavailable: {e}")
            raise
    return _enhanced_memory_manager
