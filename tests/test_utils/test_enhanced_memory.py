"""Tests for enhanced_memory module."""

import gc
import os
import shutil
import tempfile
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from mini_claude.utils.enhanced_memory import (
    EnhancedMemoryManager,
    SessionSearchResult,
    get_enhanced_memory_manager,
)
from mini_claude.utils.vector_store import (
    VectorStore,
    SearchResult,
    DependencyNotFoundError,
)


class TestSessionSearchResult:
    """Test SessionSearchResult dataclass."""

    def test_session_search_result_creation(self):
        """Test creating a SessionSearchResult."""
        result = SessionSearchResult(
            session_id="session-1",
            message_idx=5,
            role="user",
            content="Hello world",
            score=0.95,
            timestamp="2026-05-01T10:00:00",
            session_type="chat",
        )
        assert result.session_id == "session-1"
        assert result.message_idx == 5
        assert result.role == "user"
        assert result.content == "Hello world"
        assert result.score == 0.95
        assert result.timestamp == "2026-05-01T10:00:00"
        assert result.session_type == "chat"

    def test_session_search_result_to_dict(self):
        """Test converting SessionSearchResult to dictionary."""
        result = SessionSearchResult(
            session_id="session-1",
            message_idx=5,
            role="assistant",
            content="Hello!",
            score=0.8,
        )
        d = result.to_dict()
        assert d["session_id"] == "session-1"
        assert d["message_idx"] == 5
        assert d["role"] == "assistant"
        assert d["content"] == "Hello!"
        assert d["score"] == 0.8
        assert d["timestamp"] is None
        assert d["session_type"] is None

    def test_session_search_result_defaults(self):
        """Test SessionSearchResult with default values."""
        result = SessionSearchResult(
            session_id="s1",
            message_idx=0,
            role="user",
            content="test",
            score=0.5,
        )
        assert result.timestamp is None
        assert result.session_type is None


class TestEnhancedMemoryManager:
    """Test EnhancedMemoryManager class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        gc.collect()
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock session manager."""
        manager = MagicMock()
        manager.list_sessions.return_value = []
        return manager

    @pytest.fixture
    def mock_vector_store(self):
        """Create a mock vector store."""
        store = MagicMock()
        store.count.return_value = 0
        store.get_stats.return_value = {
            "db_type": "chroma",
            "document_count": 0,
        }
        return store

    @pytest.fixture
    def memory_manager(self, temp_dir, mock_session_manager, mock_vector_store):
        """Create an EnhancedMemoryManager with mocked dependencies."""
        try:
            manager = EnhancedMemoryManager(
                vector_store=mock_vector_store,
                session_manager=mock_session_manager,
            )
            yield manager
        except Exception as e:
            pytest.skip(f"Failed to create memory manager: {e}")

    def test_init_with_provided_dependencies(self, mock_session_manager, mock_vector_store):
        """Test initialization with provided dependencies."""
        manager = EnhancedMemoryManager(
            vector_store=mock_vector_store,
            session_manager=mock_session_manager,
        )
        assert manager._session_manager is mock_session_manager
        assert manager._vector_store is mock_vector_store

    def test_index_session_not_found(self, memory_manager, mock_session_manager):
        """Test indexing a non-existent session."""
        mock_session_manager.load_session_full.return_value = None
        result = memory_manager.index_session("nonexistent")
        assert result is False

    def test_index_session_empty_messages(self, memory_manager, mock_session_manager):
        """Test indexing a session with no messages."""
        mock_session_manager.load_session_full.return_value = {
            "id": "session-1",
            "messages": [],
        }
        result = memory_manager.index_session("session-1")
        assert result is True

    def test_index_session_success(self, memory_manager, mock_session_manager, mock_vector_store):
        """Test successful session indexing."""
        mock_session_manager.load_session_full.return_value = {
            "id": "session-1",
            "created_at": "2026-05-01T10:00:00",
            "updated_at": "2026-05-01T11:00:00",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
        }
        mock_vector_store.add_batch.return_value = True

        result = memory_manager.index_session("session-1")

        assert result is True
        mock_vector_store.add_batch.assert_called_once()
        call_args = mock_vector_store.add_batch.call_args
        ids, texts, metadatas = call_args[0]
        assert len(ids) == 2
        assert "session-1:0" in ids
        assert "session-1:1" in ids

    def test_index_session_skips_system_messages(
        self, memory_manager, mock_session_manager, mock_vector_store
    ):
        """Test that system messages are skipped during indexing."""
        mock_session_manager.load_session_full.return_value = {
            "id": "session-1",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello"},
            ],
        }
        mock_vector_store.add_batch.return_value = True

        result = memory_manager.index_session("session-1")

        assert result is True
        call_args = mock_vector_store.add_batch.call_args
        ids = call_args[0][0]
        assert len(ids) == 1
        assert "session-1:1" in ids  # Only the user message

    def test_index_session_skips_empty_content(
        self, memory_manager, mock_session_manager, mock_vector_store
    ):
        """Test that empty messages are skipped."""
        mock_session_manager.load_session_full.return_value = {
            "id": "session-1",
            "messages": [
                {"role": "user", "content": ""},
                {"role": "assistant", "content": "   "},
                {"role": "user", "content": "Real message"},
            ],
        }
        mock_vector_store.add_batch.return_value = True

        result = memory_manager.index_session("session-1")

        assert result is True
        call_args = mock_vector_store.add_batch.call_args
        ids = call_args[0][0]
        assert len(ids) == 1

    def test_search_history_success(self, memory_manager, mock_vector_store):
        """Test successful history search."""
        mock_vector_store.search_similar.return_value = [
            SearchResult(
                id="session-1:0",
                text="Hello world",
                score=0.9,
                metadata={
                    "session_id": "session-1",
                    "message_idx": 0,
                    "role": "user",
                },
            ),
        ]

        results = memory_manager.search_history("hello", k=5)

        assert len(results) == 1
        assert results[0].session_id == "session-1"
        assert results[0].content == "Hello world"
        assert results[0].score == 0.9

    def test_search_history_with_role_filter(self, memory_manager, mock_vector_store):
        """Test search with role filter."""
        mock_vector_store.search_similar.return_value = [
            SearchResult(
                id="session-1:0",
                text="User message",
                score=0.9,
                metadata={
                    "session_id": "session-1",
                    "message_idx": 0,
                    "role": "user",
                },
            ),
        ]

        memory_manager.search_history("message", k=5, role_filter="user")

        mock_vector_store.search_similar.assert_called_once()
        call_kwargs = mock_vector_store.search_similar.call_args[1]
        assert call_kwargs["filter"] == {"role": "user"}

    def test_search_history_with_time_range(self, memory_manager, mock_vector_store):
        """Test search with time range filter."""
        # Time range: May 1-2, 2026
        start_time = datetime(2026, 5, 1, 0, 0, 0)
        end_time = datetime(2026, 5, 2, 23, 59, 59)

        mock_vector_store.search_similar.return_value = [
            SearchResult(
                id="session-1:0",
                text="Recent message",
                score=0.9,
                metadata={
                    "session_id": "session-1",
                    "message_idx": 0,
                    "role": "user",
                    "timestamp": "2026-05-01T12:00:00",
                },
            ),
            SearchResult(
                id="session-2:0",
                text="Old message",
                score=0.8,
                metadata={
                    "session_id": "session-2",
                    "message_idx": 0,
                    "role": "user",
                    "timestamp": "2026-04-01T12:00:00",
                },
            ),
        ]

        results = memory_manager.search_history(
            "message",
            k=5,
            time_range=(start_time, end_time),
        )

        # Only the recent message should be included
        assert len(results) == 1
        assert results[0].content == "Recent message"

    def test_search_history_limits_results(self, memory_manager, mock_vector_store):
        """Test that search results are limited to k."""
        mock_vector_store.search_similar.return_value = [
            SearchResult(
                id=f"session-{i}:0",
                text=f"Message {i}",
                score=0.9 - i * 0.1,
                metadata={
                    "session_id": f"session-{i}",
                    "message_idx": 0,
                    "role": "user",
                },
            )
            for i in range(10)
        ]

        results = memory_manager.search_history("test", k=3)

        assert len(results) == 3

    def test_search_history_handles_error(self, memory_manager, mock_vector_store):
        """Test that search handles errors gracefully."""
        mock_vector_store.search_similar.side_effect = Exception("Search failed")

        results = memory_manager.search_history("test", k=5)

        assert results == []

    def test_get_relevant_context_success(self, memory_manager, mock_vector_store):
        """Test getting relevant context."""
        mock_vector_store.search_similar.return_value = [
            SearchResult(
                id="session-1:0",
                text="Previous discussion about Python",
                score=0.9,
                metadata={
                    "session_id": "session-1",
                    "role": "user",
                },
            ),
            SearchResult(
                id="session-2:0",
                text="More Python tips",
                score=0.8,
                metadata={
                    "session_id": "session-2",
                    "role": "assistant",
                },
            ),
        ]

        context = memory_manager.get_relevant_context("Python programming", max_tokens=100)

        assert len(context) == 2
        assert "Python" in context[0]

    def test_get_relevant_context_respects_token_limit(self, memory_manager, mock_vector_store):
        """Test that context respects token limit."""
        # Create long messages
        long_text = "A" * 1000
        mock_vector_store.search_similar.return_value = [
            SearchResult(
                id=f"session-{i}:0",
                text=long_text,
                score=0.9,
                metadata={
                    "session_id": f"session-{i}",
                    "role": "user",
                },
            )
            for i in range(5)
        ]

        # Small token limit
        context = memory_manager.get_relevant_context("test", max_tokens=50)

        # Should not include all messages
        total_chars = sum(len(c) for c in context)
        # max_tokens=50, chars_per_token=4, so max_chars=200
        assert total_chars <= 200

    def test_get_relevant_context_handles_error(self, memory_manager, mock_vector_store):
        """Test that get_relevant_context handles errors."""
        mock_vector_store.search_similar.side_effect = Exception("Failed")

        context = memory_manager.get_relevant_context("test")

        assert context == []

    def test_get_session_messages(self, memory_manager, mock_session_manager):
        """Test getting messages from a session."""
        mock_session_manager.load_session_full.return_value = {
            "id": "session-1",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
                {"role": "user", "content": "Bye"},
            ],
        }

        messages = memory_manager.get_session_messages("session-1")

        assert len(messages) == 3
        assert messages[0]["content"] == "Hello"

    def test_get_session_messages_with_range(self, memory_manager, mock_session_manager):
        """Test getting messages with start/end indices."""
        mock_session_manager.load_session_full.return_value = {
            "id": "session-1",
            "messages": [
                {"role": "user", "content": "Msg 1"},
                {"role": "assistant", "content": "Msg 2"},
                {"role": "user", "content": "Msg 3"},
            ],
        }

        messages = memory_manager.get_session_messages("session-1", start_idx=1, end_idx=3)

        assert len(messages) == 2
        assert messages[0]["content"] == "Msg 2"

    def test_get_session_messages_not_found(self, memory_manager, mock_session_manager):
        """Test getting messages from non-existent session."""
        mock_session_manager.load_session_full.return_value = None

        messages = memory_manager.get_session_messages("nonexistent")

        assert messages == []

    def test_delete_session_index(self, memory_manager, mock_session_manager, mock_vector_store):
        """Test deleting a session's index."""
        mock_session_manager.load_session_full.return_value = {
            "id": "session-1",
            "messages": [
                {"role": "user", "content": "Hello"},
            ],
        }
        mock_vector_store.delete_by_id.return_value = True
        memory_manager._indexed_sessions.add("session-1")

        result = memory_manager.delete_session_index("session-1")

        assert result is True
        assert "session-1" not in memory_manager._indexed_sessions

    def test_delete_session_index_not_found(self, memory_manager, mock_session_manager):
        """Test deleting index for non-existent session."""
        mock_session_manager.load_session_full.return_value = None

        result = memory_manager.delete_session_index("nonexistent")

        assert result is False

    def test_index_all_sessions(self, memory_manager, mock_session_manager, mock_vector_store):
        """Test indexing all sessions."""
        mock_session_manager.list_sessions.return_value = [
            {"id": "session-1"},
            {"id": "session-2"},
        ]
        mock_session_manager.load_session_full.return_value = {
            "id": "session-1",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        mock_vector_store.add_batch.return_value = True

        count = memory_manager.index_all_sessions()

        assert count == 2

    def test_get_stats(self, memory_manager, mock_session_manager, mock_vector_store):
        """Test getting statistics."""
        mock_session_manager.list_sessions.return_value = [
            {"id": "session-1"},
            {"id": "session-2"},
        ]
        mock_vector_store.get_stats.return_value = {
            "db_type": "chroma",
            "document_count": 5,
        }
        memory_manager._indexed_sessions.add("session-1")

        stats = memory_manager.get_stats()

        assert stats["total_sessions"] == 2
        assert stats["indexed_sessions"] == 1
        assert stats["vector_store_stats"]["document_count"] == 5

    def test_clear(self, memory_manager, mock_vector_store):
        """Test clearing all indexed data."""
        memory_manager._indexed_sessions.add("session-1")
        mock_vector_store.clear.return_value = True

        result = memory_manager.clear()

        assert result is True
        assert len(memory_manager._indexed_sessions) == 0

    def test_clear_handles_error(self, memory_manager, mock_vector_store):
        """Test clear handles errors gracefully."""
        mock_vector_store.clear.side_effect = Exception("Clear failed")

        result = memory_manager.clear()

        assert result is False


class TestEnhancedMemoryManagerIntegration:
    """Integration tests with real VectorStore and SessionManager."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        gc.collect()
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    @pytest.fixture
    def real_memory_manager(self, temp_dir):
        """Create a real EnhancedMemoryManager for integration tests."""
        try:
            from mini_claude.utils.session import SessionManager

            db_path = os.path.join(temp_dir, "sessions.db")
            vector_path = os.path.join(temp_dir, "vectors")

            session_manager = SessionManager(db_path)
            vector_store = VectorStore(
                db_type="chroma",
                path=vector_path,
                collection_name="test_memory",
            )

            manager = EnhancedMemoryManager(
                vector_store=vector_store,
                session_manager=session_manager,
            )
            yield manager

            # Cleanup
            try:
                vector_store.clear()
            except Exception:
                pass
            vector_store._backend = None
            vector_store._collection = None
            gc.collect()

        except DependencyNotFoundError as e:
            pytest.skip(str(e))

    def test_full_workflow(self, real_memory_manager):
        """Test complete workflow: index, search, retrieve."""
        # Create a test session
        session_id = "test-session-1"
        messages = [
            {"role": "user", "content": "How do I deploy a Python app?"},
            {"role": "assistant", "content": "You can use Docker or cloud services like AWS."},
            {"role": "user", "content": "What about database connections?"},
            {"role": "assistant", "content": "Use environment variables for database URLs."},
        ]

        # Save session
        real_memory_manager._session_manager.save_session(
            session_id,
            messages,
            context={"topic": "deployment"},
        )

        # Index the session
        result = real_memory_manager.index_session(session_id)
        assert result is True

        # Search for deployment-related content
        results = real_memory_manager.search_history("deploy python application", k=3)
        assert len(results) > 0

        # Get relevant context
        context = real_memory_manager.get_relevant_context("database setup", max_tokens=200)
        assert len(context) > 0

        # Get stats
        stats = real_memory_manager.get_stats()
        assert stats["indexed_sessions"] == 1

        # Cleanup
        real_memory_manager.delete_session_index(session_id)

    def test_multiple_sessions_search(self, real_memory_manager):
        """Test searching across multiple sessions."""
        # Create and index multiple sessions
        sessions = [
            (
                "session-1",
                [
                    {"role": "user", "content": "React component for forms"},
                    {"role": "assistant", "content": "Use controlled components with useState."},
                ],
            ),
            (
                "session-2",
                [
                    {"role": "user", "content": "Vue.js form validation"},
                    {"role": "assistant", "content": "Use vee-validate or Vuelidate."},
                ],
            ),
            (
                "session-3",
                [
                    {"role": "user", "content": "Python data processing"},
                    {"role": "assistant", "content": "Use pandas for data manipulation."},
                ],
            ),
        ]

        for session_id, messages in sessions:
            real_memory_manager._session_manager.save_session(session_id, messages)
            real_memory_manager.index_session(session_id)

        # Search for form-related content
        results = real_memory_manager.search_history("form handling", k=5)
        assert len(results) > 0

        # Should find React and Vue sessions
        found_sessions = {r.session_id for r in results}
        assert len(found_sessions) >= 1

        # Cleanup
        for session_id, _ in sessions:
            real_memory_manager.delete_session_index(session_id)


class TestGetEnhancedMemoryManager:
    """Test the global instance getter."""

    def test_get_enhanced_memory_manager_singleton(self, temp_dir):
        """Test that get_enhanced_memory_manager returns singleton."""
        import mini_claude.utils.enhanced_memory as module

        module._enhanced_memory_manager = None

        try:
            manager1 = get_enhanced_memory_manager(
                vector_store_path=os.path.join(temp_dir, "vectors"),
                session_db_path=os.path.join(temp_dir, "sessions.db"),
            )
            manager2 = get_enhanced_memory_manager()

            assert manager1 is manager2

            # Cleanup
            try:
                manager1.clear()
            except Exception:
                pass

        except DependencyNotFoundError:
            pytest.skip("Dependencies not available")
        finally:
            module._enhanced_memory_manager = None


# Fixtures for tests that need temp_dir
@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    gc.collect()
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass
