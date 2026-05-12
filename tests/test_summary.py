"""Tests for session summary functionality."""

import pytest
import tempfile
import os

from mini_claude.utils.token_manager import TokenCounter
from mini_claude.utils.memory import SessionMemory
from mini_claude.utils.session import SessionManager


class TestTokenCounterSummary:
    """TokenCounter summary functionality tests."""

    @pytest.fixture
    def token_counter(self):
        return TokenCounter(model="deepseek-chat")

    def test_count_tokens(self, token_counter):
        """Test token counting."""
        text = "你好，这是一个测试消息。"
        count = token_counter.count_tokens(text)
        assert count > 0

    def test_count_message_tokens(self, token_counter):
        """Test message token counting."""
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"}
        ]
        total = token_counter.count_messages_tokens(messages)
        assert total > 0

    def test_get_usage_stats(self, token_counter):
        """Test usage stats."""
        messages = [
            {"role": "user", "content": "测试消息" * 100}
        ]
        stats = token_counter.get_usage_stats(messages)
        assert "current_tokens" in stats
        assert "token_budget" in stats
        assert "usage_percent" in stats
        assert stats["current_tokens"] > 0

    def test_check_budget_within_limit(self, token_counter):
        """Test budget check when within limit."""
        messages = [{"role": "user", "content": "短消息"}]
        result = token_counter.check_budget(messages)
        assert result["ok"] is True

    def test_truncate_messages(self, token_counter):
        """Test message truncation."""
        messages = [
            {"role": "system", "content": "系统提示"}
        ] + [
            {"role": "user", "content": f"消息 {i}"}
            for i in range(30)
        ]

        truncated = token_counter.truncate_messages(messages, keep_first=1, keep_last=4)
        assert len(truncated) < len(messages)
        # First message (system) should be kept
        assert truncated[0]["role"] == "system"

    @pytest.mark.asyncio
    async def test_summarize_messages_returns_tuple(self, token_counter):
        """Test that summarize_messages returns a tuple (messages, summary)."""
        # Only 3 messages, keep_first=1, keep_last=2 means 1+2=3
        # So len(messages) <= keep_first + keep_last, no summarization
        messages = [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "问题1"},
            {"role": "assistant", "content": "回答1"},
        ]

        # Mock LLM chat function
        async def mock_llm_chat(messages, **kwargs):
            return {"choices": [{"message": {"content": "这是测试摘要"}}]}

        compressed, summary = await token_counter.summarize_messages(
            messages,
            llm_chat_func=mock_llm_chat,
            keep_first=1,
            keep_last=2,
        )

        assert isinstance(compressed, list)
        assert len(compressed) == 3  # All messages kept
        assert summary is None  # No summarization happened

    @pytest.mark.asyncio
    async def test_summarize_messages_with_enough_messages(self, token_counter):
        """Test summarization with enough messages."""
        messages = [
            {"role": "system", "content": "系统提示"},
        ] + [
            {"role": "user", "content": f"问题 {i} " * 50}
            for i in range(10)
        ] + [
            {"role": "assistant", "content": f"回答 {i} " * 50}
            for i in range(10)
        ]

        # Mock LLM chat function
        async def mock_llm_chat(messages, **kwargs):
            return {"choices": [{"message": {"content": "用户询问了多个问题，助手提供了相应回答。"}}]}

        compressed, summary = await token_counter.summarize_messages(
            messages,
            llm_chat_func=mock_llm_chat,
            keep_first=1,
            keep_last=4,
        )

        assert isinstance(compressed, list)
        assert len(compressed) < len(messages)
        assert summary is not None
        assert "历史对话摘要" in compressed[1]["content"]


class TestSessionMemory:
    """SessionMemory tests."""

    def test_session_memory_creation(self):
        """Test SessionMemory creation."""
        memory = SessionMemory(thread_id="test-123")
        assert memory.thread_id == "test-123"
        assert memory.messages == []
        assert memory.summary is None

    def test_session_memory_with_summary(self):
        """Test SessionMemory with summary."""
        memory = SessionMemory(
            thread_id="test-123",
            summary="这是一个测试摘要"
        )
        assert memory.summary == "这是一个测试摘要"

    def test_add_message(self):
        """Test adding messages."""
        memory = SessionMemory(thread_id="test-123")
        memory.add_message("user", "你好")
        assert len(memory.messages) == 1
        assert memory.messages[0]["role"] == "user"
        assert memory.messages[0]["content"] == "你好"

    def test_get_recent_messages(self):
        """Test getting recent messages."""
        memory = SessionMemory(thread_id="test-123")
        for i in range(10):
            memory.add_message("user", f"消息 {i}")

        recent = memory.get_recent_messages(5)
        assert len(recent) == 5
        assert recent[0]["content"] == "消息 5"

    def test_to_system_message(self):
        """Test converting summary to system message."""
        memory = SessionMemory(
            thread_id="test-123",
            summary="这是历史对话摘要"
        )

        sys_msg = memory.to_system_message()
        assert sys_msg is not None
        assert sys_msg["role"] == "system"
        assert "<conversation_summary>" in sys_msg["content"]
        assert "这是历史对话摘要" in sys_msg["content"]

    def test_to_system_message_no_summary(self):
        """Test to_system_message when no summary."""
        memory = SessionMemory(thread_id="test-123")
        sys_msg = memory.to_system_message()
        assert sys_msg is None

    def test_get_context_messages(self):
        """Test getting context messages with summary."""
        memory = SessionMemory(
            thread_id="test-123",
            summary="历史摘要"
        )
        memory.add_message("user", "新问题")

        context = memory.get_context_messages()
        assert len(context) == 2
        assert context[0]["role"] == "system"
        assert context[1]["role"] == "user"

    def test_get_context_messages_no_summary(self):
        """Test getting context messages without summary."""
        memory = SessionMemory(thread_id="test-123")
        memory.add_message("user", "问题")

        context = memory.get_context_messages()
        assert len(context) == 1
        assert context[0]["role"] == "user"

    def test_to_dict(self):
        """Test converting to dictionary."""
        memory = SessionMemory(
            thread_id="test-123",
            summary="摘要",
            total_tokens=100
        )
        data = memory.to_dict()
        assert data["thread_id"] == "test-123"
        assert data["summary"] == "摘要"
        assert data["total_tokens"] == 100


class TestSessionManager:
    """SessionManager tests."""

    @pytest.fixture
    def session_manager(self):
        """Create a session manager with temp database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        manager = SessionManager(db_path)
        yield manager
        # Cleanup
        try:
            os.unlink(db_path)
        except Exception:
            pass

    def test_save_and_load_session(self, session_manager):
        """Test saving and loading a session."""
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"}
        ]

        session_manager.save_session("test-1", messages)
        loaded, summary = session_manager.load_session("test-1")

        assert loaded == messages
        assert summary is None

    def test_save_session_with_summary(self, session_manager):
        """Test saving a session with summary."""
        messages = [{"role": "user", "content": "测试"}]
        summary = "这是一个测试摘要"

        session_manager.save_session("test-2", messages, summary=summary)
        loaded, loaded_summary = session_manager.load_session("test-2")

        assert loaded == messages
        assert loaded_summary == summary

    def test_save_session_with_token_count(self, session_manager):
        """Test saving a session with token count."""
        messages = [{"role": "user", "content": "测试"}]

        session_manager.save_session("test-3", messages, token_count=100)
        full = session_manager.load_session_full("test-3")

        assert full["token_count"] == 100
        assert full["compressed_at"] is None  # No summary, so no compressed_at

    def test_save_session_compressed_at(self, session_manager):
        """Test that compressed_at is set when summary is provided."""
        messages = [{"role": "user", "content": "测试"}]
        summary = "摘要"

        session_manager.save_session("test-4", messages, summary=summary)
        full = session_manager.load_session_full("test-4")

        assert full["summary"] == summary
        assert full["compressed_at"] is not None

    def test_load_nonexistent_session(self, session_manager):
        """Test loading a nonexistent session."""
        loaded, summary = session_manager.load_session("nonexistent")
        assert loaded is None
        assert summary is None

    def test_list_sessions(self, session_manager):
        """Test listing sessions."""
        session_manager.save_session("session-1", [{"role": "user", "content": "a"}])
        session_manager.save_session("session-2", [{"role": "user", "content": "b"}])

        sessions = session_manager.list_sessions()
        assert len(sessions) == 2
        ids = [s["id"] for s in sessions]
        assert "session-1" in ids
        assert "session-2" in ids

    def test_delete_session(self, session_manager):
        """Test deleting a session."""
        session_manager.save_session("to-delete", [{"role": "user", "content": "test"}])

        deleted = session_manager.delete_session("to-delete")
        assert deleted is True

        loaded, _ = session_manager.load_session("to-delete")
        assert loaded is None

    def test_load_session_full(self, session_manager):
        """Test loading full session data."""
        messages = [{"role": "user", "content": "测试"}]
        summary = "摘要"

        session_manager.save_session(
            "full-test",
            messages,
            summary=summary,
            token_count=50
        )

        full = session_manager.load_session_full("full-test")
        assert full["id"] == "full-test"
        assert full["messages"] == messages
        assert full["summary"] == summary
        assert full["token_count"] == 50
        assert "created_at" in full
        assert "updated_at" in full


class TestIntegration:
    """Integration tests for summary functionality."""

    @pytest.fixture
    def session_manager(self):
        """Create a session manager with temp database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        manager = SessionManager(db_path)
        yield manager
        try:
            os.unlink(db_path)
        except Exception:
            pass

    def test_full_summary_workflow(self, session_manager):
        """Test the full summary workflow."""
        # 1. Create messages
        messages = [
            {"role": "user", "content": f"问题 {i}"}
            for i in range(25)
        ]

        # 2. Save with summary
        summary = "用户提出了多个问题"
        session_manager.save_session("workflow-test", messages, summary=summary)

        # 3. Load and verify
        loaded, loaded_summary = session_manager.load_session("workflow-test")
        assert len(loaded) == 25
        assert loaded_summary == summary

        # 4. Load full and check metadata
        full = session_manager.load_session_full("workflow-test")
        assert full["compressed_at"] is not None

    def test_session_memory_integration(self):
        """Test SessionMemory integration with summary."""
        # 1. Create memory with messages
        memory = SessionMemory(thread_id="integration-test")
        for i in range(10):
            memory.add_message("user", f"消息 {i}")
            memory.add_message("assistant", f"回复 {i}")

        # 2. Set summary
        memory.summary = "用户进行了多轮对话"

        # 3. Get context messages
        context = memory.get_context_messages()
        assert len(context) == 21  # 1 summary + 20 messages

        # 4. Verify summary is first
        assert context[0]["role"] == "system"
        assert "<conversation_summary>" in context[0]["content"]
