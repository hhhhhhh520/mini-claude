"""Tests for ExecutionState and checkpoint recovery."""

import pytest
import tempfile
import os

from mini_claude.agent.state import ExecutionState
from mini_claude.utils.session import SessionManager


# ========== ExecutionState Tests (15个) ==========


class TestExecutionStateCreation:
    """Test ExecutionState creation and validation."""

    def test_create_execution_state_basic(self):
        """Test basic ExecutionState creation."""
        state = ExecutionState()
        assert state.current_node == ""
        assert state.iteration_count == 0
        assert state.last_error is None
        assert state.pending_tools == []
        assert state.checkpoint_data == {}

    def test_create_execution_state_with_values(self):
        """Test ExecutionState creation with values."""
        state = ExecutionState(
            current_node="act",
            iteration_count=5,
            last_error="Test error",
            pending_tools=["read_file", "write_file"],
            checkpoint_data={"thread_id": "test-123"},
        )
        assert state.current_node == "act"
        assert state.iteration_count == 5
        assert state.last_error == "Test error"
        assert len(state.pending_tools) == 2
        assert state.checkpoint_data["thread_id"] == "test-123"

    def test_execution_state_timestamps(self):
        """Test that timestamps are automatically set."""
        state = ExecutionState()
        assert state.created_at is not None
        assert state.updated_at is not None

    def test_execution_state_to_dict(self):
        """Test serialization to dictionary."""
        state = ExecutionState(
            current_node="think",
            iteration_count=3,
            last_error="Error",
            pending_tools=["tool1"],
            checkpoint_data={"key": "value"},
        )
        data = state.to_dict()

        assert data["current_node"] == "think"
        assert data["iteration_count"] == 3
        assert data["last_error"] == "Error"
        assert data["pending_tools"] == ["tool1"]
        assert data["checkpoint_data"] == {"key": "value"}

    def test_execution_state_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "current_node": "observe",
            "iteration_count": 10,
            "last_error": "Some error",
            "pending_tools": ["a", "b"],
            "checkpoint_data": {"x": 1},
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-02T00:00:00",
        }
        state = ExecutionState.from_dict(data)

        assert state.current_node == "observe"
        assert state.iteration_count == 10
        assert state.last_error == "Some error"
        assert state.pending_tools == ["a", "b"]
        assert state.checkpoint_data == {"x": 1}

    def test_execution_state_roundtrip(self):
        """Test serialization roundtrip."""
        original = ExecutionState(
            current_node="plan",
            iteration_count=7,
            last_error="Test",
            pending_tools=["x", "y", "z"],
            checkpoint_data={"nested": {"key": "value"}},
        )
        data = original.to_dict()
        restored = ExecutionState.from_dict(data)

        assert restored.current_node == original.current_node
        assert restored.iteration_count == original.iteration_count
        assert restored.last_error == original.last_error
        assert restored.pending_tools == original.pending_tools
        assert restored.checkpoint_data == original.checkpoint_data


class TestExecutionStateValidation:
    """Test ExecutionState validation."""

    def test_is_valid_with_node(self):
        """Test validation passes with current_node."""
        state = ExecutionState(current_node="think")
        assert state.is_valid() is True

    def test_is_valid_with_checkpoint_data(self):
        """Test validation passes with checkpoint_data."""
        state = ExecutionState(checkpoint_data={"thread_id": "x"})
        assert state.is_valid() is True

    def test_is_invalid_empty_state(self):
        """Test validation fails for empty state."""
        state = ExecutionState()
        assert state.is_valid() is False

    def test_is_invalid_negative_iteration(self):
        """Test validation fails for negative iteration count."""
        state = ExecutionState(current_node="think", iteration_count=-1)
        assert state.is_valid() is False

    def test_is_valid_zero_iteration(self):
        """Test validation passes for zero iteration count."""
        state = ExecutionState(current_node="think", iteration_count=0)
        assert state.is_valid() is True

    def test_update_timestamp(self):
        """Test update_timestamp modifies updated_at."""
        state = ExecutionState(current_node="test")
        old_updated = state.updated_at

        # Small delay to ensure timestamp changes
        import time

        time.sleep(0.01)

        state.update_timestamp()
        assert state.updated_at != old_updated


# ========== SessionManager Execution State Tests (15个) ==========


class TestSessionManagerExecutionState:
    """Test SessionManager execution state methods."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        # Cleanup
        try:
            os.unlink(db_path)
        except OSError:
            pass

    def test_save_execution_state_new_session(self, temp_db):
        """Test saving execution state for a new session."""
        manager = SessionManager(temp_db)
        state = ExecutionState(current_node="act", iteration_count=3, last_error="Test error")

        result = manager.save_execution_state("test-session", state)
        assert result is True

    def test_load_execution_state(self, temp_db):
        """Test loading execution state."""
        manager = SessionManager(temp_db)
        original = ExecutionState(
            current_node="observe",
            iteration_count=5,
            last_error="Error",
            pending_tools=["tool1", "tool2"],
            checkpoint_data={"key": "value"},
        )

        manager.save_execution_state("test-id", original)
        loaded = manager.load_execution_state("test-id")

        assert loaded is not None
        assert loaded.current_node == "observe"
        assert loaded.iteration_count == 5
        assert loaded.last_error == "Error"
        assert loaded.pending_tools == ["tool1", "tool2"]

    def test_load_execution_state_not_found(self, temp_db):
        """Test loading non-existent execution state."""
        manager = SessionManager(temp_db)
        loaded = manager.load_execution_state("nonexistent")
        assert loaded is None

    def test_clear_execution_state(self, temp_db):
        """Test clearing execution state."""
        manager = SessionManager(temp_db)
        state = ExecutionState(current_node="test", iteration_count=1)

        manager.save_execution_state("test-id", state)
        manager.clear_execution_state("test-id")

        loaded = manager.load_execution_state("test-id")
        assert loaded is None

    def test_update_execution_state(self, temp_db):
        """Test updating existing execution state."""
        manager = SessionManager(temp_db)

        # Save initial state
        state1 = ExecutionState(current_node="think", iteration_count=1)
        manager.save_execution_state("test-id", state1)

        # Update with new state
        state2 = ExecutionState(current_node="act", iteration_count=2)
        manager.save_execution_state("test-id", state2)

        loaded = manager.load_execution_state("test-id")
        assert loaded.current_node == "act"
        assert loaded.iteration_count == 2

    def test_list_interrupted_sessions_empty(self, temp_db):
        """Test listing interrupted sessions when none exist."""
        manager = SessionManager(temp_db)
        interrupted = manager.list_interrupted_sessions()
        assert interrupted == []

    def test_list_interrupted_sessions_with_data(self, temp_db):
        """Test listing interrupted sessions."""
        manager = SessionManager(temp_db)

        # Create multiple sessions with execution states
        for i in range(3):
            state = ExecutionState(
                current_node=f"node_{i}",
                iteration_count=i * 2,
                last_error="Error" if i == 1 else None,
            )
            manager.save_execution_state(f"session_{i}", state)

        interrupted = manager.list_interrupted_sessions()
        assert len(interrupted) == 3

        # Check structure
        for s in interrupted:
            assert "id" in s
            assert "current_node" in s
            assert "iteration_count" in s
            assert "has_error" in s

    def test_execution_state_with_session_messages(self, temp_db):
        """Test execution state stored alongside messages."""
        manager = SessionManager(temp_db)

        # Save session with messages
        messages = [{"role": "user", "content": "Hello"}]
        manager.save_session("test-id", messages)

        # Add execution state
        state = ExecutionState(current_node="plan", iteration_count=2)
        manager.save_execution_state("test-id", state)

        # Load both
        loaded_msgs, _ = manager.load_session("test-id")
        loaded_state = manager.load_execution_state("test-id")

        assert loaded_msgs == messages
        assert loaded_state.current_node == "plan"

    def test_execution_state_invalid_json(self, temp_db):
        """Test handling of corrupted execution state JSON."""
        manager = SessionManager(temp_db)

        # Insert invalid JSON directly
        with manager._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sessions (id, created_at, updated_at, messages, execution_state) "
                "VALUES (?, ?, ?, '[]', ?)",
                ("corrupted", "2024-01-01", "2024-01-01", "invalid json{"),
            )

        loaded = manager.load_execution_state("corrupted")
        assert loaded is None

    def test_execution_state_preserves_unicode(self, temp_db):
        """Test that Unicode is preserved in execution state."""
        manager = SessionManager(temp_db)

        state = ExecutionState(current_node="observe", last_error="错误信息: 中文测试")
        manager.save_execution_state("unicode-test", state)

        loaded = manager.load_execution_state("unicode-test")
        assert loaded.last_error == "错误信息: 中文测试"

    def test_execution_state_large_pending_tools(self, temp_db):
        """Test execution state with many pending tools."""
        manager = SessionManager(temp_db)

        tools = [f"tool_{i}" for i in range(100)]
        state = ExecutionState(current_node="act", pending_tools=tools)
        manager.save_execution_state("many-tools", state)

        loaded = manager.load_execution_state("many-tools")
        assert len(loaded.pending_tools) == 100

    def test_execution_state_nested_checkpoint_data(self, temp_db):
        """Test execution state with nested checkpoint data."""
        manager = SessionManager(temp_db)

        checkpoint = {
            "thread_id": "test-123",
            "config": {"recursion_limit": 50, "model": "gpt-4"},
            "nested": {"deep": {"value": 42}},
        }
        state = ExecutionState(current_node="check_completion", checkpoint_data=checkpoint)
        manager.save_execution_state("nested-data", state)

        loaded = manager.load_execution_state("nested-data")
        assert loaded.checkpoint_data["nested"]["deep"]["value"] == 42

    def test_list_interrupted_sessions_excludes_invalid(self, temp_db):
        """Test that invalid execution states are excluded."""
        manager = SessionManager(temp_db)

        # Valid state
        valid = ExecutionState(current_node="think", iteration_count=1)
        manager.save_execution_state("valid-session", valid)

        # Invalid state (empty - no node, no checkpoint)
        invalid = ExecutionState(iteration_count=0)
        manager.save_execution_state("invalid-session", invalid)

        interrupted = manager.list_interrupted_sessions()
        assert len(interrupted) == 1
        assert interrupted[0]["id"] == "valid-session"


# ========== Integration Tests (10个) ==========


class TestCheckpointRecoveryIntegration:
    """Integration tests for checkpoint recovery."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        try:
            os.unlink(db_path)
        except OSError:
            pass

    def test_full_recovery_workflow(self, temp_db):
        """Test complete recovery workflow."""
        manager = SessionManager(temp_db)

        # Simulate saving state during execution
        state = ExecutionState(
            current_node="act",
            iteration_count=5,
            last_error="API rate limit",
            pending_tools=["write_file", "run_tests"],
            checkpoint_data={"thread_id": "recovery-test"},
        )
        manager.save_execution_state("interrupted-session", state)

        # Simulate loading for recovery
        loaded = manager.load_execution_state("interrupted-session")
        assert loaded.is_valid() is True
        assert loaded.current_node == "act"
        assert loaded.iteration_count == 5

        # Clear after successful recovery
        manager.clear_execution_state("interrupted-session")
        assert manager.load_execution_state("interrupted-session") is None

    def test_recovery_after_session_update(self, temp_db):
        """Test recovery when session is updated."""
        manager = SessionManager(temp_db)

        # Initial save
        messages = [{"role": "user", "content": "Start"}]
        manager.save_session("session-1", messages)

        # Save execution state
        state = ExecutionState(current_node="plan", iteration_count=2)
        manager.save_execution_state("session-1", state)

        # Update messages (e.g., after some processing)
        messages.append({"role": "assistant", "content": "Response"})
        manager.save_session("session-1", messages)

        # Execution state should still be loadable
        loaded_state = manager.load_execution_state("session-1")
        loaded_msgs, _ = manager.load_session("session-1")

        assert loaded_state is not None
        assert len(loaded_msgs) == 2

    def test_multiple_sessions_recovery(self, temp_db):
        """Test recovery of multiple sessions."""
        manager = SessionManager(temp_db)

        # Create multiple interrupted sessions
        for i in range(5):
            state = ExecutionState(
                current_node=f"node_{i}",
                iteration_count=i,
                last_error=f"Error {i}" if i % 2 == 0 else None,
            )
            manager.save_execution_state(f"session_{i}", state)

        # List all interrupted
        interrupted = manager.list_interrupted_sessions()
        assert len(interrupted) == 5

        # Recover specific one
        loaded = manager.load_execution_state("session_3")
        assert loaded.iteration_count == 3

    def test_state_persistence_across_manager_instances(self, temp_db):
        """Test that state persists across different manager instances."""
        manager1 = SessionManager(temp_db)
        state = ExecutionState(
            current_node="observe", iteration_count=10, checkpoint_data={"key": "persistent"}
        )
        manager1.save_execution_state("persistent-test", state)

        # Create new manager instance
        manager2 = SessionManager(temp_db)
        loaded = manager2.load_execution_state("persistent-test")

        assert loaded.current_node == "observe"
        assert loaded.checkpoint_data["key"] == "persistent"

    def test_concurrent_state_updates(self, temp_db):
        """Test concurrent updates to execution state."""
        manager = SessionManager(temp_db)

        # First save
        state1 = ExecutionState(current_node="think", iteration_count=1)
        manager.save_execution_state("concurrent-test", state1)

        # Second save (overwrites)
        state2 = ExecutionState(current_node="plan", iteration_count=2)
        manager.save_execution_state("concurrent-test", state2)

        # Third save (overwrites again)
        state3 = ExecutionState(current_node="act", iteration_count=3)
        manager.save_execution_state("concurrent-test", state3)

        loaded = manager.load_execution_state("concurrent-test")
        assert loaded.current_node == "act"
        assert loaded.iteration_count == 3

    def test_recovery_with_empty_error(self, temp_db):
        """Test recovery when last_error is None."""
        manager = SessionManager(temp_db)

        state = ExecutionState(current_node="check_completion", iteration_count=4, last_error=None)
        manager.save_execution_state("no-error-session", state)

        loaded = manager.load_execution_state("no-error-session")
        assert loaded.last_error is None
        assert loaded.is_valid() is True

    def test_recovery_list_sorted_by_updated(self, temp_db):
        """Test that interrupted sessions list is sorted by update time."""
        import time

        manager = SessionManager(temp_db)

        # Create sessions with delays to ensure different timestamps
        for name in ["oldest", "middle", "newest"]:
            state = ExecutionState(current_node="test")
            manager.save_execution_state(name, state)
            time.sleep(0.01)  # Small delay to ensure different timestamps

        interrupted = manager.list_interrupted_sessions()
        assert interrupted[0]["id"] == "newest"  # Most recent first

    def test_delete_session_clears_execution_state(self, temp_db):
        """Test that deleting a session also clears execution state."""
        manager = SessionManager(temp_db)

        # Create session with messages and execution state
        manager.save_session("to-delete", [{"role": "user", "content": "test"}])
        state = ExecutionState(current_node="test")
        manager.save_execution_state("to-delete", state)

        # Delete session
        manager.delete_session("to-delete")

        # Execution state should also be gone
        loaded = manager.load_execution_state("to-delete")
        assert loaded is None

    def test_empty_pending_tools_list(self, temp_db):
        """Test handling of empty pending tools list."""
        manager = SessionManager(temp_db)

        state = ExecutionState(current_node="observe", pending_tools=[])
        manager.save_execution_state("empty-tools", state)

        loaded = manager.load_execution_state("empty-tools")
        assert loaded.pending_tools == []

    def test_execution_state_with_special_characters(self, temp_db):
        """Test execution state with special characters in error message."""
        manager = SessionManager(temp_db)

        state = ExecutionState(
            current_node="handle_error",
            last_error="Error: 'quotes' and \"double quotes\" and \n newlines",
        )
        manager.save_execution_state("special-chars", state)

        loaded = manager.load_execution_state("special-chars")
        assert "'" in loaded.last_error
        assert '"' in loaded.last_error
        assert "\n" in loaded.last_error
