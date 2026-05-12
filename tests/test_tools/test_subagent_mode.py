"""Tests for subagent mode and result extraction."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from mini_claude.tools.file_ops import (
    set_current_agent,
    get_current_agent,
    set_subagent_mode,
    is_subagent_mode,
)
from mini_claude.tools.agent_spawn import SpawnAgentTool


class TestSubagentModeFunctions:
    """Test subagent mode functions."""

    def test_default_subagent_mode(self):
        """Test default subagent mode is False."""
        # Reset to default
        set_subagent_mode(False)
        assert is_subagent_mode() is False

    def test_set_subagent_mode_true(self):
        """Test setting subagent mode to True."""
        set_subagent_mode(True)
        assert is_subagent_mode() is True
        # Reset
        set_subagent_mode(False)

    def test_set_subagent_mode_false(self):
        """Test setting subagent mode to False."""
        set_subagent_mode(True)
        set_subagent_mode(False)
        assert is_subagent_mode() is False

    def test_current_agent_default(self):
        """Test default current agent is 'main'."""
        assert get_current_agent() == "main"

    def test_set_current_agent(self):
        """Test setting current agent."""
        set_current_agent("test_agent")
        assert get_current_agent() == "test_agent"
        # Reset
        set_current_agent("main")


class TestExtractSubagentResult:
    """Test _extract_subagent_result method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tool = SpawnAgentTool()

    def test_extract_ai_response(self):
        """Test extracting AI response when present."""
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="User task"),
            AIMessage(content="", tool_calls=[{"id": "1", "name": "web_search", "args": {}}]),
            HumanMessage(content="Tool web_search result: Search results here", name="web_search"),
            AIMessage(content="Based on the search, here are the findings..."),
        ]
        result = self.tool._extract_subagent_result(messages)
        assert "Based on the search" in result

    def test_extract_tool_results_when_no_ai_response(self):
        """Test extracting tool results when no AI summary."""
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="User task"),
            AIMessage(content="", tool_calls=[{"id": "1", "name": "web_search", "args": {}}]),
            HumanMessage(content="Tool web_search result: Result 1", name="web_search"),
            HumanMessage(content="Tool read_file result: Result 2", name="read_file"),
        ]
        result = self.tool._extract_subagent_result(messages)
        assert "Result 1" in result
        assert "Result 2" in result

    def test_extract_fallback_to_last_message(self):
        """Test fallback to last message when no tool results."""
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="User task"),
        ]
        result = self.tool._extract_subagent_result(messages)
        assert result == "User task"

    def test_extract_empty_messages(self):
        """Test with empty message list."""
        result = self.tool._extract_subagent_result([])
        assert result == "No result"

    def test_extract_skips_ai_with_tool_calls(self):
        """Test that AI messages with tool_calls are skipped."""
        messages = [
            HumanMessage(content="Task"),
            AIMessage(content="", tool_calls=[{"id": "1", "name": "tool", "args": {}}]),
            HumanMessage(content="Tool result", name="tool"),
            # This AI message has tool_calls, should be skipped
            AIMessage(
                content="Should be skipped", tool_calls=[{"id": "2", "name": "another", "args": {}}]
            ),
        ]
        result = self.tool._extract_subagent_result(messages)
        assert "Tool result" in result
        assert "Should be skipped" not in result

    def test_extract_multiple_tool_results_joined(self):
        """Test multiple tool results are joined with newlines."""
        messages = [
            HumanMessage(content="Task"),
            HumanMessage(content="Result 1", name="tool1"),
            HumanMessage(content="Result 2", name="tool2"),
            HumanMessage(content="Result 3", name="tool3"),
        ]
        result = self.tool._extract_subagent_result(messages)
        assert "Result 1" in result
        assert "Result 2" in result
        assert "Result 3" in result
        assert "\n\n" in result  # Results are joined with double newlines

    def test_extract_prioritizes_ai_summary_over_tool_results(self):
        """Test that AI summary is prioritized over tool results."""
        messages = [
            HumanMessage(content="Task"),
            HumanMessage(content="Long tool result...", name="tool"),
            AIMessage(content="Summary of results"),
        ]
        result = self.tool._extract_subagent_result(messages)
        assert result == "Summary of results"
        assert "Long tool result" not in result


class TestSubagentModeIntegration:
    """Test subagent mode integration with tools."""

    def test_subagent_mode_flag_exists(self):
        """Test that subagent mode flag can be imported."""
        from mini_claude.tools import set_subagent_mode, is_subagent_mode

        assert callable(set_subagent_mode)
        assert callable(is_subagent_mode)

    def test_agent_context_functions_exported(self):
        """Test that agent context functions are exported."""
        from mini_claude.tools import (
            set_current_agent,
            get_current_agent,
            set_subagent_mode,
            is_subagent_mode,
        )

        assert callable(set_current_agent)
        assert callable(get_current_agent)
        assert callable(set_subagent_mode)
        assert callable(is_subagent_mode)
