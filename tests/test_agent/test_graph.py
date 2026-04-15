"""Tests for agent graph."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from mini_claude.agent.state import AgentState, create_initial_state
from mini_claude.agent.nodes import think_node, should_continue_router


def test_create_initial_state():
    """Test creating initial state."""
    state = create_initial_state("Hello", thread_id="test")

    assert state["current_task"] == "Hello"
    assert state["thread_id"] == "test"
    assert state["iteration"] == 0
    assert state["should_continue"] is True
    assert len(state["messages"]) == 1


def test_should_continue_router():
    """Test the continue router."""
    state_true = AgentState(should_continue=True)
    state_false = AgentState(should_continue=False)

    assert should_continue_router(state_true) is True
    assert should_continue_router(state_false) is False


@pytest.mark.asyncio
async def test_think_node():
    """Test the think node."""
    state = create_initial_state("Test task")

    result = await think_node(state)

    assert result["iteration"] == 1
    assert len(result["messages"]) > 0
    # Should have system message added
    from langchain_core.messages import SystemMessage
    assert any(isinstance(m, SystemMessage) for m in result["messages"])
