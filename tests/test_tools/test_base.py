"""Tests for base tool functionality including examples feature."""

import pytest
from typing import Dict, Any, List

from mini_claude.tools.base import BaseTool, ToolRegistry


class MockTool(BaseTool):
    """Mock tool for testing."""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "A mock tool for testing"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Test input"},
            },
            "required": ["input"],
        }

    async def execute(self, input: str) -> str:
        return f"Executed: {input}"

    @property
    def examples(self) -> List[Dict[str, Any]]:
        return [
            {
                "description": "Basic usage example",
                "input": {"input": "hello"},
                "expected_output": "Executed: hello",
            }
        ]


class MockToolNoExamples(BaseTool):
    """Mock tool without examples."""

    @property
    def name(self) -> str:
        return "no_examples_tool"

    @property
    def description(self) -> str:
        return "A tool without examples"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self) -> str:
        return "Done"


# ========== BaseTool Examples Tests ==========


class TestBaseToolExamples:
    """Test BaseTool examples functionality."""

    def test_tool_has_examples_property(self):
        """Test that tool has examples property."""
        tool = MockTool()
        assert hasattr(tool, "examples")
        assert isinstance(tool.examples, list)

    def test_examples_structure(self):
        """Test that examples have correct structure."""
        tool = MockTool()
        examples = tool.examples
        assert len(examples) > 0

        example = examples[0]
        assert "description" in example
        assert "input" in example
        assert "expected_output" in example

    def test_tool_without_examples_returns_empty_list(self):
        """Test that tool without examples returns empty list."""
        tool = MockToolNoExamples()
        # Should have default empty examples
        assert tool.examples == []

    def test_to_dict_includes_examples(self):
        """Test that to_dict includes examples field."""
        tool = MockTool()
        tool_dict = tool.to_dict()

        assert "examples" in tool_dict
        assert isinstance(tool_dict["examples"], list)
        assert len(tool_dict["examples"]) > 0

    def test_to_dict_examples_match_property(self):
        """Test that to_dict examples match examples property."""
        tool = MockTool()
        tool_dict = tool.to_dict()

        assert tool_dict["examples"] == tool.examples

    def test_example_description_is_string(self):
        """Test that example description is a string."""
        tool = MockTool()
        for example in tool.examples:
            assert isinstance(example["description"], str)
            assert len(example["description"]) > 0

    def test_example_input_is_dict(self):
        """Test that example input is a dictionary."""
        tool = MockTool()
        for example in tool.examples:
            assert isinstance(example["input"], dict)

    def test_example_expected_output_is_string(self):
        """Test that example expected_output is a string."""
        tool = MockTool()
        for example in tool.examples:
            assert isinstance(example["expected_output"], str)


# ========== Core Tool Examples Tests ==========


class TestReadFileToolExamples:
    """Test ReadFileTool examples."""

    def test_read_file_has_examples(self):
        """Test that ReadFileTool has examples."""
        from mini_claude.tools.file_ops import ReadFileTool

        tool = ReadFileTool()
        assert hasattr(tool, "examples")
        assert len(tool.examples) >= 2

    def test_read_file_example_structure(self):
        """Test ReadFileTool example structure."""
        from mini_claude.tools.file_ops import ReadFileTool

        tool = ReadFileTool()
        for example in tool.examples:
            assert "description" in example
            assert "input" in example
            assert "expected_output" in example
            assert "path" in example["input"]

    def test_read_file_examples_cover_common_cases(self):
        """Test that examples cover common use cases."""
        from mini_claude.tools.file_ops import ReadFileTool

        tool = ReadFileTool()
        descriptions = [ex["description"] for ex in tool.examples]

        # Should have at least basic file reading example
        assert any("basic" in d.lower() or "read" in d.lower() for d in descriptions)


class TestWriteFileToolExamples:
    """Test WriteFileTool examples."""

    def test_write_file_has_examples(self):
        """Test that WriteFileTool has examples."""
        from mini_claude.tools.file_ops import WriteFileTool

        tool = WriteFileTool()
        assert hasattr(tool, "examples")
        assert len(tool.examples) >= 2

    def test_write_file_example_structure(self):
        """Test WriteFileTool example structure."""
        from mini_claude.tools.file_ops import WriteFileTool

        tool = WriteFileTool()
        for example in tool.examples:
            assert "description" in example
            assert "input" in example
            assert "expected_output" in example
            assert "path" in example["input"]
            assert "content" in example["input"]


class TestRunCommandToolExamples:
    """Test RunCommandTool examples."""

    def test_run_command_has_examples(self):
        """Test that RunCommandTool has examples."""
        from mini_claude.tools.bash import RunCommandTool

        tool = RunCommandTool()
        assert hasattr(tool, "examples")
        assert len(tool.examples) >= 2

    def test_run_command_example_structure(self):
        """Test RunCommandTool example structure."""
        from mini_claude.tools.bash import RunCommandTool

        tool = RunCommandTool()
        for example in tool.examples:
            assert "description" in example
            assert "input" in example
            assert "expected_output" in example
            assert "command" in example["input"]


class TestWebSearchToolExamples:
    """Test WebSearchTool examples."""

    def test_web_search_has_examples(self):
        """Test that WebSearchTool has examples."""
        from mini_claude.tools.web_search import WebSearchTool

        tool = WebSearchTool()
        assert hasattr(tool, "examples")
        assert len(tool.examples) >= 2

    def test_web_search_example_structure(self):
        """Test WebSearchTool example structure."""
        from mini_claude.tools.web_search import WebSearchTool

        tool = WebSearchTool()
        for example in tool.examples:
            assert "description" in example
            assert "input" in example
            assert "expected_output" in example
            assert "query" in example["input"]


class TestSpawnAgentToolExamples:
    """Test SpawnAgentTool examples."""

    def test_spawn_agent_has_examples(self):
        """Test that SpawnAgentTool has examples."""
        from mini_claude.tools.agent_spawn import SpawnAgentTool

        tool = SpawnAgentTool()
        assert hasattr(tool, "examples")
        assert len(tool.examples) >= 2

    def test_spawn_agent_example_structure(self):
        """Test SpawnAgentTool example structure."""
        from mini_claude.tools.agent_spawn import SpawnAgentTool

        tool = SpawnAgentTool()
        for example in tool.examples:
            assert "description" in example
            assert "input" in example
            assert "expected_output" in example
            assert "task" in example["input"]


# ========== ToolRegistry Tests ==========


class TestToolRegistryWithExamples:
    """Test ToolRegistry with examples support."""

    def test_registry_get_all_definitions_includes_examples(self):
        """Test that get_all_definitions includes examples."""
        registry = ToolRegistry()
        registry.register(MockTool())

        definitions = registry.get_all_definitions()
        assert len(definitions) == 1
        assert "examples" in definitions[0]

    def test_registry_tool_dict_complete(self):
        """Test that tool dict is complete with all fields."""
        registry = ToolRegistry()
        registry.register(MockTool())

        definitions = registry.get_all_definitions()
        tool_dict = definitions[0]

        assert "name" in tool_dict
        assert "description" in tool_dict
        assert "parameters" in tool_dict
        assert "examples" in tool_dict


# ========== Integration Tests ==========


class TestToolExamplesIntegration:
    """Integration tests for tool examples."""

    def test_all_core_tools_have_examples(self):
        """Test that all core tools have examples defined."""
        from mini_claude.tools.file_ops import ReadFileTool, WriteFileTool
        from mini_claude.tools.bash import RunCommandTool
        from mini_claude.tools.web_search import WebSearchTool
        from mini_claude.tools.agent_spawn import SpawnAgentTool

        core_tools = [
            ReadFileTool(),
            WriteFileTool(),
            RunCommandTool(),
            WebSearchTool(),
            SpawnAgentTool(),
        ]

        for tool in core_tools:
            assert hasattr(tool, "examples"), f"{tool.name} missing examples property"
            assert len(tool.examples) >= 2, f"{tool.name} should have at least 2 examples"

    def test_examples_are_valid_json_schema_inputs(self):
        """Test that example inputs match parameter schema."""
        from mini_claude.tools.file_ops import ReadFileTool, WriteFileTool
        from mini_claude.tools.bash import RunCommandTool

        tools = [ReadFileTool(), WriteFileTool(), RunCommandTool()]

        for tool in tools:
            params_schema = tool.parameters
            required_params = params_schema.get("required", [])
            properties = params_schema.get("properties", {})

            for example in tool.examples:
                example_input = example["input"]

                # Check required parameters are present in example
                for req_param in required_params:
                    assert req_param in example_input, (
                        f"{tool.name}: Required param '{req_param}' missing from example"
                    )

                # Check example input parameters are valid
                for param_name in example_input:
                    assert param_name in properties, (
                        f"{tool.name}: Unknown param '{param_name}' in example"
                    )
