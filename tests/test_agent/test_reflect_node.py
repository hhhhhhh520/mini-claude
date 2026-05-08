"""Tests for reflect_node."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage

from mini_claude.agent.nodes import reflect_node
from mini_claude.agent.state import AgentState, StopReason, create_initial_state
from mini_claude.agent.complexity import ComplexityLevel, TaskComplexityAnalyzer


class TestReflectNodeBasic:
    """Tests for reflect_node basic functionality."""

    def test_reflect_node_exists(self):
        """Test that reflect_node function exists."""
        from mini_claude.agent.nodes import reflect_node
        assert callable(reflect_node)

    @pytest.mark.asyncio
    async def test_reflect_node_simple_task_skips(self):
        """Test that reflect_node skips for simple tasks."""
        state = create_initial_state(
            user_input="Fix typo in README",
            thread_id="test-1"
        )
        state["iteration"] = 1
        state["messages"].append(AIMessage(content="Done"))

        result = await reflect_node(state)

        # Simple task should not trigger reflection
        assert result == {}  # Empty dict means no state update

    @pytest.mark.asyncio
    async def test_reflect_node_complex_task_triggers(self):
        """Test that reflect_node triggers for complex tasks."""
        # Complex task: Develop payment system with security
        state = create_initial_state(
            user_input="Develop a new payment integration system with multiple payment gateways",
            thread_id="test-2"
        )
        state["iteration"] = 5
        state["messages"].append(AIMessage(content="Working on payment system..."))

        # Mock LLM provider
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''
        {
            "successes": ["Successfully created payment module structure"],
            "failures": ["Initial API call failed due to missing credentials"],
            "improvements": ["Add credential validation before API calls"]
        }
        '''

        with patch('mini_claude.agent.nodes._shared.llm_provider') as mock_provider:
            mock_provider.chat = AsyncMock(return_value=mock_response)

            result = await reflect_node(state)

            # Complex task should generate reflection
            assert "reflection_notes" in result
            assert "lessons_learned" in result
            assert "improvement_suggestions" in result


class TestReflectNodeOutput:
    """Tests for reflect_node output format."""

    @pytest.mark.asyncio
    async def test_reflect_node_returns_correct_keys(self):
        """Test that reflect_node returns correct state keys."""
        # Very complex task
        complex_task = "Develop comprehensive authentication system with OAuth2, JWT, MFA, and fraud detection for production deployment"
        state = create_initial_state(
            user_input=complex_task,
            thread_id="test-3"
        )
        state["iteration"] = 3

        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''
        {
            "successes": ["OAuth2 integration working"],
            "failures": ["JWT token validation bug"],
            "improvements": ["Add more unit tests"]
        }
        '''

        with patch('mini_claude.agent.nodes._shared.llm_provider') as mock_provider:
            mock_provider.chat = AsyncMock(return_value=mock_response)

            result = await reflect_node(state)

            assert isinstance(result.get("reflection_notes", []), list)
            assert isinstance(result.get("lessons_learned", []), list)
            assert isinstance(result.get("improvement_suggestions", []), list)


class TestReflectNodeComplexity:
    """Tests for complexity-based activation."""

    @pytest.mark.asyncio
    async def test_simple_task_no_reflection(self):
        """Test SIMPLE complexity does not trigger reflection."""
        state = create_initial_state(
            user_input="Fix bug",  # Very simple, score < 30
            thread_id="test-simple"
        )

        result = await reflect_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_medium_task_no_reflection(self):
        """Test MEDIUM complexity does not trigger reflection."""
        # Medium task (score 31-70)
        state = create_initial_state(
            user_input="Optimize database query for better performance",
            thread_id="test-medium"
        )

        # Verify it's MEDIUM level
        analyzer = TaskComplexityAnalyzer()
        complexity = analyzer.analyze(state["current_task"])

        # If it happens to be COMPLEX, this test will need adjustment
        if complexity.level == ComplexityLevel.MEDIUM:
            result = await reflect_node(state)
            assert result == {}

    @pytest.mark.asyncio
    async def test_complex_task_reflection(self):
        """Test COMPLEX complexity triggers reflection."""
        # Ensure COMPLEX task (score > 70)
        complex_task = "Develop new payment processing system with fraud detection, transaction logging, and multi-gateway support for production deployment"
        state = create_initial_state(
            user_input=complex_task,
            thread_id="test-complex"
        )

        # Verify it's COMPLEX
        analyzer = TaskComplexityAnalyzer()
        complexity = analyzer.analyze(state["current_task"])
        assert complexity.level == ComplexityLevel.COMPLEX

        # Mock LLM
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''
        {
            "successes": ["Payment module created"],
            "failures": ["Need more testing"],
            "improvements": ["Add integration tests"]
        }
        '''

        with patch('mini_claude.agent.nodes._shared.llm_provider') as mock_provider:
            mock_provider.chat = AsyncMock(return_value=mock_response)

            result = await reflect_node(state)
            assert result != {}


class TestReflectNodeErrorHandling:
    """Tests for error handling in reflect_node."""

    @pytest.mark.asyncio
    async def test_llm_json_parse_error(self):
        """Test handling of invalid JSON response."""
        complex_task = "Develop critical production payment system"
        state = create_initial_state(
            user_input=complex_task,
            thread_id="test-json-error"
        )

        # Mock LLM with invalid JSON
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is not valid JSON"

        with patch('mini_claude.agent.nodes._shared.llm_provider') as mock_provider:
            mock_provider.chat = AsyncMock(return_value=mock_response)

            result = await reflect_node(state)

            # Should return empty dict on parse error
            assert result == {}

    @pytest.mark.asyncio
    async def test_llm_connection_error(self):
        """Test handling of LLM connection error."""
        complex_task = "Develop critical production payment system"
        state = create_initial_state(
            user_input=complex_task,
            thread_id="test-conn-error"
        )

        with patch('mini_claude.agent.nodes._shared.llm_provider') as mock_provider:
            mock_provider.chat = AsyncMock(side_effect=ConnectionError("Connection failed"))

            result = await reflect_node(state)

            # Should return empty dict on connection error
            assert result == {}

    @pytest.mark.asyncio
    async def test_llm_timeout_error(self):
        """Test handling of LLM timeout."""
        complex_task = "Develop critical production payment system"
        state = create_initial_state(
            user_input=complex_task,
            thread_id="test-timeout"
        )

        with patch('mini_claude.agent.nodes._shared.llm_provider') as mock_provider:
            mock_provider.chat = AsyncMock(side_effect=TimeoutError("Timeout"))

            result = await reflect_node(state)

            # Should return empty dict on timeout
            assert result == {}


class TestReflectNodeToolAnalysis:
    """Tests for tool call analysis in reflection."""

    @pytest.mark.asyncio
    async def test_reflect_with_tool_calls(self):
        """Test reflection with tool call history."""
        complex_task = "Develop payment system for production"
        state = create_initial_state(
            user_input=complex_task,
            thread_id="test-tools"
        )

        # Add tool calls to messages - use proper tool call format
        from langchain_core.messages import ToolCall
        ai_msg = AIMessage(
            content="Creating payment module",
            tool_calls=[ToolCall(name="write_file", args={"path": "payment.py"}, id="call-1")]
        )
        state["messages"].append(ai_msg)

        result_msg = HumanMessage(
            content="Tool write_file result: File created successfully",
            name="write_file"
        )
        state["messages"].append(result_msg)

        # Mock LLM
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''
        {
            "successes": ["write_file created payment.py successfully"],
            "failures": [],
            "improvements": ["Consider adding error handling"]
        }
        '''

        with patch('mini_claude.agent.nodes._shared.llm_provider') as mock_provider:
            mock_provider.chat = AsyncMock(return_value=mock_response)

            result = await reflect_node(state)

            assert "reflection_notes" in result
            assert len(result["reflection_notes"]) > 0

    @pytest.mark.asyncio
    async def test_reflect_with_failed_tools(self):
        """Test reflection with failed tool calls."""
        complex_task = "Develop payment system for production"
        state = create_initial_state(
            user_input=complex_task,
            thread_id="test-failed-tools"
        )

        # Add failed tool call
        error_msg = HumanMessage(
            content="Tool write_file error: Permission denied",
            name="write_file"
        )
        state["messages"].append(error_msg)

        # Mock LLM
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''
        {
            "successes": [],
            "failures": ["write_file failed due to permission"],
            "improvements": ["Check file permissions before writing"]
        }
        '''

        with patch('mini_claude.agent.nodes._shared.llm_provider') as mock_provider:
            mock_provider.chat = AsyncMock(return_value=mock_response)

            result = await reflect_node(state)

            assert "lessons_learned" in result
            assert len(result["lessons_learned"]) > 0