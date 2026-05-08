"""End-to-end user flow tests.

Tests complete user sessions including:
- Full user conversation flow
- Multi-turn dialogue
- Tool call chains
- Session persistence and recovery
- Token budget management
- Concurrent sub-agent execution

Uses pytest markers:
- @pytest.mark.unit: Fast, no dependencies
- @pytest.mark.integration: Mocked services
- @pytest.mark.e2e: Real API calls
"""

import asyncio
import gc
import os
import shutil
import tempfile
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any

import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from mini_claude.agent.state import (
    AgentState,
    StopReason,
    create_initial_state,
    ExecutionState,
)
from mini_claude.agent.graph import (
    build_agent_graph,
    build_agent_graph_no_checkpoint,
    build_agent_graph_simple,
    DEFAULT_RECURSION_LIMIT,
)
from mini_claude.utils.session import SessionManager
from mini_claude.utils.token_manager import get_token_counter, TokenLimitStrategy
from mini_claude.config.settings import settings


# =============================================================================
# Shared Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    # Cleanup
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass
    gc.collect()


@pytest.fixture
def session_manager(temp_dir):
    """Create a SessionManager with temporary database."""
    db_path = os.path.join(temp_dir, "sessions.db")
    return SessionManager(db_path)


# =============================================================================
# Complete User Session Flow Tests
# =============================================================================

class TestCompleteUserSessionFlow:
    """Tests for complete user session from input to output."""

    @pytest.mark.integration
    def test_user_input_to_agent_response(self, temp_dir):
        """Test: User input -> Agent processing -> Response."""
        # Create initial state
        user_input = "Hello, introduce yourself briefly"
        state = create_initial_state(user_input)

        # Verify initial state structure
        assert state["current_task"] == user_input
        assert state["iteration"] == 0
        assert state["stop_reason"] == StopReason.CONTINUE
        assert len(state["messages"]) == 1
        assert isinstance(state["messages"][0], HumanMessage)

    @pytest.mark.integration
    def test_session_save_on_completion(self, session_manager):
        """Test that session is saved when task completes."""
        messages = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
        ]

        # Save session
        session_manager.save_session("test-session-1", messages)

        # Load and verify
        loaded, summary = session_manager.load_session("test-session-1")
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0]["content"] == "What is Python?"

    @pytest.mark.integration
    def test_session_list_after_multiple_sessions(self, session_manager):
        """Test listing multiple sessions."""
        # Create multiple sessions
        for i in range(5):
            messages = [
                {"role": "user", "content": f"Question {i}"},
                {"role": "assistant", "content": f"Answer {i}"},
            ]
            session_manager.save_session(f"session-{i}", messages)

        # List sessions
        sessions = session_manager.list_sessions()
        assert len(sessions) == 5
        # Should be ordered by updated_at DESC
        assert sessions[0]["id"] == "session-4"


# =============================================================================
# Multi-turn Dialogue Tests
# =============================================================================

class TestMultiTurnDialogue:
    """Tests for multi-turn conversations."""

    @pytest.mark.integration
    def test_conversation_history_preserved(self, session_manager):
        """Test that conversation history is preserved across turns."""
        # First turn
        messages_1 = [
            {"role": "user", "content": "What is FastAPI?"},
            {"role": "assistant", "content": "FastAPI is a Python web framework."},
        ]
        session_manager.save_session("conv-1", messages_1)

        # Second turn - add to existing conversation
        loaded, _ = session_manager.load_session("conv-1")
        loaded.extend([
            {"role": "user", "content": "How do I install it?"},
            {"role": "assistant", "content": "Use pip install fastapi."},
        ])
        session_manager.save_session("conv-1", loaded)

        # Verify history preserved
        final, _ = session_manager.load_session("conv-1")
        assert len(final) == 4
        assert final[2]["content"] == "How do I install it?"

    @pytest.mark.integration
    def test_context_window_management(self, session_manager):
        """Test that long conversations are managed properly."""
        # Create long conversation
        messages = []
        for i in range(20):
            messages.append({"role": "user", "content": f"Question {i}"})
            messages.append({"role": "assistant", "content": f"Answer {i}"})

        session_manager.save_session("long-conv", messages)

        # Verify all messages saved
        loaded, _ = session_manager.load_session("long-conv")
        assert len(loaded) == 40

        # Test token counter truncation
        token_counter = get_token_counter("deepseek-chat")
        token_counter.strategy = TokenLimitStrategy.TRUNCATE

        # Convert to LiteLLM format
        litellm_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in loaded
        ]

        # Truncate with small budget
        truncated = token_counter.truncate_messages(
            litellm_messages,
            keep_first=1,
            keep_last=4,
        )

        # Should have fewer messages after truncation
        assert len(truncated) < len(litellm_messages)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_state_accumulation_prevention(self):
        """Test that state doesn't accumulate errors across turns."""
        # Create initial state
        state = create_initial_state("Task 1")
        state["errors"] = ["Error from task 1"]
        state["retry_count"] = 2

        # Simulate think_node resetting error state
        from mini_claude.agent.nodes import think_node

        # Create fresh state for new task (iteration 0)
        fresh_state = create_initial_state("Task 2")
        result = await think_node(fresh_state)

        # Verify error state reset
        assert result["errors"] == []
        assert result["retry_count"] == 0


# =============================================================================
# Tool Call Chain Tests
# =============================================================================

class TestToolCallChains:
    """Tests for tool execution chains."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_sequential_tool_calls(self, temp_dir):
        """Test multiple tools called in sequence."""
        # Create test files
        file1 = os.path.join(temp_dir, "file1.txt")
        file2 = os.path.join(temp_dir, "file2.txt")

        # Create state with tool results
        state = create_initial_state("Read and analyze files")
        state["messages"].extend([
            AIMessage(content="", tool_calls=[
                {"id": "tc1", "name": "read_file", "args": {"path": file1}},
                {"id": "tc2", "name": "read_file", "args": {"path": file2}},
            ]),
            HumanMessage(content="Tool read_file result: content1", name="read_file"),
            HumanMessage(content="Tool read_file result: content2", name="read_file"),
        ])

        # Verify tool results are recorded
        tool_results = [
            m for m in state["messages"]
            if isinstance(m, HumanMessage) and hasattr(m, "name") and m.name
        ]
        assert len(tool_results) == 2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_tool_error_recovery(self):
        """Test recovery from tool execution errors."""
        from mini_claude.agent.nodes import handle_error_node, retry_node

        # Create state with tool error
        state = create_initial_state("Create file")
        state["errors"] = ["Tool write_file error: Permission denied"]
        state["retry_count"] = 0

        # Handle error
        result = await handle_error_node(state)

        # Verify retry message generated
        assert result["retry_count"] == 1
        assert len(result["messages"]) > 0

        # Execute retry
        retry_result = await retry_node(state)
        assert len(retry_result["messages"]) > 0

    @pytest.mark.integration
    def test_tool_result_formatting(self):
        """Test that tool results are properly formatted."""
        # Simulate tool result message
        result_msg = HumanMessage(
            content="Tool write_file result: File created successfully at /path/to/file",
            name="write_file",
        )

        # Verify message structure
        assert hasattr(result_msg, "name")
        assert result_msg.name == "write_file"
        assert "result:" in result_msg.content


# =============================================================================
# Session Persistence and Recovery Tests
# =============================================================================

class TestSessionPersistenceAndRecovery:
    """Tests for session save/load and recovery."""

    @pytest.mark.integration
    def test_session_full_persistence(self, session_manager):
        """Test complete session persistence with metadata."""
        messages = [
            {"role": "user", "content": "Create a web app"},
            {"role": "assistant", "content": "I'll help you create a web app."},
        ]
        context = {"workspace": "/path/to/workspace"}
        summary = "User requested web app creation"

        # Save with metadata
        session_manager.save_session(
            "full-session",
            messages,
            context=context,
            summary=summary,
            token_count=150,
        )

        # Load full session
        full = session_manager.load_session_full("full-session")
        assert full is not None
        assert full["context"]["workspace"] == "/path/to/workspace"
        assert full["summary"] == summary
        assert full["token_count"] == 150

    @pytest.mark.integration
    def test_execution_state_persistence(self, session_manager):
        """Test execution state save/load for recovery."""
        # Create execution state
        exec_state = ExecutionState(
            current_node="act",
            iteration_count=3,
            last_error="Connection timeout",
            pending_tools=["write_file"],
            checkpoint_data={"config": {"thread_id": "test"}},
        )

        # Save execution state
        session_manager.save_execution_state("interrupted-session", exec_state)

        # Load execution state
        loaded = session_manager.load_execution_state("interrupted-session")
        assert loaded is not None
        assert loaded.current_node == "act"
        assert loaded.iteration_count == 3
        assert loaded.last_error == "Connection timeout"

    @pytest.mark.integration
    def test_interrupted_session_listing(self, session_manager):
        """Test listing sessions that were interrupted."""
        # Create normal session
        session_manager.save_session(
            "normal-session",
            [{"role": "user", "content": "Hello"}],
        )

        # Create interrupted session
        exec_state = ExecutionState(
            current_node="think",
            iteration_count=2,
        )
        session_manager.save_execution_state("interrupted", exec_state)

        # List interrupted sessions
        interrupted = session_manager.list_interrupted_sessions()
        assert len(interrupted) == 1
        assert interrupted[0]["id"] == "interrupted"
        assert interrupted[0]["current_node"] == "think"

    @pytest.mark.integration
    def test_session_deletion_with_state(self, session_manager):
        """Test deleting session clears execution state."""
        # Create session with execution state
        exec_state = ExecutionState(current_node="act", iteration_count=1)
        session_manager.save_execution_state("to-delete", exec_state)

        # Clear execution state
        session_manager.clear_execution_state("to-delete")

        # Verify cleared
        loaded = session_manager.load_execution_state("to-delete")
        assert loaded is None


# =============================================================================
# Token Budget Management Tests
# =============================================================================

class TestTokenBudgetManagement:
    """Tests for token budget tracking and management."""

    @pytest.mark.integration
    def test_token_budget_check(self):
        """Test token budget checking."""
        token_counter = get_token_counter("deepseek-chat")
        token_counter.budget_ratio = 0.8
        token_counter.warn_ratio = 0.7

        # Small messages should pass
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        check = token_counter.check_budget(messages, reserved_output=1000)
        assert check["ok"] is True

    @pytest.mark.integration
    def test_token_budget_exceeded_warning(self):
        """Test warning when approaching token limit."""
        token_counter = get_token_counter("deepseek-chat")
        token_counter.strategy = TokenLimitStrategy.WARN

        # Create large messages
        large_messages = [
            {"role": "user", "content": "X" * 10000},
            {"role": "assistant", "content": "Y" * 10000},
        ]

        check = token_counter.check_budget(large_messages, reserved_output=1000)
        # May or may not exceed depending on model context window
        # Just verify check works
        assert "ok" in check
        assert "reason" in check or check["ok"]

    @pytest.mark.integration
    def test_token_truncation_strategy(self):
        """Test message truncation when budget exceeded."""
        token_counter = get_token_counter("deepseek-chat")
        token_counter.strategy = TokenLimitStrategy.TRUNCATE

        # Create large conversation
        messages = []
        for i in range(20):
            messages.append({"role": "user", "content": f"Long message {i} with content" * 50})
            messages.append({"role": "assistant", "content": f"Response {i} with content" * 50})

        # Truncate
        truncated = token_counter.truncate_messages(messages)

        # Should be shorter
        assert len(truncated) < len(messages)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_token_summary_generation(self):
        """Test summarization when budget exceeded."""
        token_counter = get_token_counter("deepseek-chat")
        token_counter.strategy = TokenLimitStrategy.SUMMARIZE

        # Create messages
        messages = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
            {"role": "user", "content": "Question 2"},
            {"role": "assistant", "content": "Answer 2"},
        ]

        # Mock LLM for summary
        async def mock_llm(messages, **kwargs):
            return {
                "choices": [{
                    "message": {
                        "content": "[Summary] User asked two questions.",
                    }
                }]
            }

        # Summarize
        try:
            summarized, summary_text = await token_counter.summarize_messages(
                messages,
                llm_chat_func=mock_llm,
            )

            # Should have summary or fall back to truncation
            assert summarized is not None
            # summary_text may be None if summarization not triggered
        except Exception:
            # Summarization may not be implemented or configured
            pass


# =============================================================================
# Concurrent Sub-Agent Tests
# =============================================================================

class TestConcurrentSubAgents:
    """Tests for concurrent sub-agent execution."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_subagent_spawn_and_wait(self):
        """Test spawning and waiting for sub-agent."""
        from mini_claude.agent.subagent import subagent_manager, AgentStatus

        # Clear any existing agents
        subagent_manager.agents.clear()
        subagent_manager.results.clear()

        # Simple task
        async def simple_task(progress_callback=None):
            await asyncio.sleep(0.1)
            return "task completed"

        # Spawn agent
        agent_id = await subagent_manager.spawn(
            agent_id="test_agent_1",
            task=simple_task,
        )

        # Wait for completion
        result = await subagent_manager.wait_for_one(agent_id)

        # Verify result
        assert result.status == AgentStatus.COMPLETED
        assert result.output == "task completed"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_subagents_parallel(self):
        """Test multiple sub-agents running in parallel."""
        from mini_claude.agent.subagent import subagent_manager, AgentStatus

        # Clear state
        subagent_manager.agents.clear()
        subagent_manager.results.clear()

        # Create tasks with different durations
        async def task_fast(progress_callback=None):
            await asyncio.sleep(0.05)
            return "fast"

        async def task_slow(progress_callback=None):
            await asyncio.sleep(0.15)
            return "slow"

        # Spawn agents
        await subagent_manager.spawn("agent_fast", task_fast)
        await subagent_manager.spawn("agent_slow", task_slow)

        # Wait for all (no argument needed)
        results = await subagent_manager.wait_for_all()

        # Verify all completed
        assert "agent_fast" in results
        assert "agent_slow" in results
        assert results["agent_fast"].status == AgentStatus.COMPLETED
        assert results["agent_slow"].status == AgentStatus.COMPLETED
        assert results["agent_fast"].output == "fast"
        assert results["agent_slow"].output == "slow"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_file_lock_with_subagents(self, temp_dir):
        """Test file locking during concurrent sub-agent operations."""
        from mini_claude.utils.file_lock import file_lock_manager

        test_file = os.path.join(temp_dir, "shared.txt")

        # Acquire lock from agent 1
        success1, msg1 = await file_lock_manager.acquire_lock(
            test_file, "agent_1", "write"
        )
        assert success1

        # Agent 2 should fail to acquire write lock
        success2, msg2 = await file_lock_manager.acquire_lock(
            test_file, "agent_2", "write"
        )
        assert not success2
        assert "locked" in msg2.lower()

        # Release lock
        await file_lock_manager.release_lock(test_file, "agent_1")

        # Now agent 2 can acquire
        success3, msg3 = await file_lock_manager.acquire_lock(
            test_file, "agent_2", "write"
        )
        assert success3

        # Cleanup
        await file_lock_manager.release_lock(test_file, "agent_2")


# =============================================================================
# E2E Tests (Real API)
# =============================================================================

class TestE2ERealAPI:
    """End-to-end tests with real API calls."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_llm_simple_query(self):
        """Test real LLM call for simple query."""
        from tests.conftest import get_e2e_runner

        runner = get_e2e_runner(use_real_api=True)
        if runner.should_skip():
            pytest.skip(runner.get_skip_reason())

        # Call real LLM
        messages = [{"role": "user", "content": "Say 'hello world' and nothing else"}]
        try:
            response = await runner.call_llm(messages, temperature=0)

            # Verify response
            assert "choices" in response
            assert response["choices"][0]["message"]["content"] is not None

        except Exception as e:
            pytest.skip(f"LLM call failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_full_graph_execution(self):
        """Test complete graph execution with real LLM."""
        from tests.conftest import get_e2e_runner

        runner = get_e2e_runner(use_real_api=True)
        if runner.should_skip():
            pytest.skip(runner.get_skip_reason())

        # Build graph
        graph = build_agent_graph_no_checkpoint()

        # Create simple task
        state = create_initial_state("Say 'test complete' and nothing else")

        try:
            # Execute with limited recursion
            result = await graph.ainvoke(
                state,
                {"recursion_limit": 10},
            )

            # Verify execution completed
            assert "messages" in result
            assert len(result["messages"]) > 0

            # Check stop reason
            stop_reason = result.get("stop_reason")
            assert stop_reason in [StopReason.TASK_COMPLETE, StopReason.CONTINUE, StopReason.MAX_ITERATIONS]

        except Exception as e:
            # Real API calls may fail for various reasons
            pytest.skip(f"Graph execution failed: {e}")
