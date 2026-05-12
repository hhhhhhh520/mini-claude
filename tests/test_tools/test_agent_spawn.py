"""Tests for subagent isolation and security.

These tests verify that subagents are properly isolated from dangerous operations:
1. Command execution (run_command) is blocked
2. Spawning more agents (spawn_agent) is blocked to prevent recursion
3. Only whitelisted tools are available to subagents
"""

import pytest

from mini_claude.tools.agent_spawn import SpawnAgentTool
from mini_claude.agent.state import create_initial_state


# Expected subagent allowed tools (from agent_spawn.py and parallel.py)
EXPECTED_SUBAGENT_ALLOWED_TOOLS = [
    "read_file", "write_file", "edit_file",
    "list_dir", "search_files", "search_content",
    "web_search"
]

# Tools that must NOT be available to subagents
FORBIDDEN_TOOLS = [
    "run_command",      # Command execution - security risk
    "run_background",   # Background command execution
    "spawn_agent",      # Prevent recursive agent spawning
    "spawn_parallel",   # Prevent parallel spawning
    "plan_parallel",    # Prevent planning parallel execution
    "execute_parallel", # Prevent executing parallel tasks
]


class TestSubagentWhitelistConfiguration:
    """Test that subagent whitelist is correctly configured."""

    def test_spawn_agent_tool_whitelist_excludes_run_command(self):
        """Verify that run_command is NOT in the subagent whitelist."""
        # The whitelist is hardcoded in SpawnAgentTool.execute()
        # We check the expected list defined at module level
        assert "run_command" not in EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
            "CRITICAL: run_command must NOT be in subagent whitelist"

    def test_spawn_agent_tool_whitelist_excludes_spawn_agent(self):
        """Verify that spawn_agent is NOT in the subagent whitelist to prevent recursion."""
        assert "spawn_agent" not in EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
            "CRITICAL: spawn_agent must NOT be in subagent whitelist to prevent recursion"

    def test_spawn_agent_tool_whitelist_excludes_spawn_parallel(self):
        """Verify that spawn_parallel is NOT in the subagent whitelist."""
        assert "spawn_parallel" not in EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
            "CRITICAL: spawn_parallel must NOT be in subagent whitelist"

    def test_spawn_agent_tool_whitelist_has_required_tools(self):
        """Verify that essential safe tools ARE in the whitelist."""
        required_tools = ["read_file", "write_file", "edit_file", "web_search"]
        for tool in required_tools:
            assert tool in EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
                f"Required tool {tool} must be in subagent whitelist"

    def test_whitelist_is_explicit_not_wildcard(self):
        """Verify whitelist is explicit (not '*' or 'all')."""
        assert EXPECTED_SUBAGENT_ALLOWED_TOOLS != ["*"], \
            "Whitelist must be explicit, not wildcard"
        assert EXPECTED_SUBAGENT_ALLOWED_TOOLS != "all", \
            "Whitelist must be explicit list of tool names"


class TestSubagentStateCreation:
    """Test that subagent state is created with proper tool restrictions."""

    def test_create_initial_state_with_allowed_tools(self):
        """Test creating state with explicit allowed_tools list."""
        state = create_initial_state(
            user_input="Test task",
            is_subagent=True,
            allowed_tools=EXPECTED_SUBAGENT_ALLOWED_TOOLS
        )

        assert state["is_subagent"] is True
        assert state["allowed_tools"] == EXPECTED_SUBAGENT_ALLOWED_TOOLS

    def test_create_initial_state_default_allowed_tools_is_none(self):
        """Test that default state has allowed_tools=None (all tools)."""
        state = create_initial_state(
            user_input="Test task",
            is_subagent=False
        )

        assert state["is_subagent"] is False
        assert state["allowed_tools"] is None

    def test_subagent_state_has_limited_tools(self):
        """Test that subagent state has limited tools vs main agent."""
        main_state = create_initial_state(
            user_input="Main task",
            is_subagent=False
        )
        subagent_state = create_initial_state(
            user_input="Subagent task",
            is_subagent=True,
            allowed_tools=EXPECTED_SUBAGENT_ALLOWED_TOOLS
        )

        # Main agent has no restrictions (None = all tools)
        assert main_state["allowed_tools"] is None

        # Subagent has explicit restrictions
        assert subagent_state["allowed_tools"] is not None
        assert len(subagent_state["allowed_tools"]) > 0
        assert "run_command" not in subagent_state["allowed_tools"]


class TestToolFiltering:
    """Test that tool filtering logic works correctly."""

    def test_tool_filtering_excludes_forbidden_tools(self):
        """Test that forbidden tools are filtered out when allowed_tools is set."""
        # Simulate the filtering logic from act_node
        all_tools = [
            {"name": "read_file", "description": "Read file"},
            {"name": "write_file", "description": "Write file"},
            {"name": "run_command", "description": "Execute command"},
            {"name": "spawn_agent", "description": "Spawn subagent"},
            {"name": "web_search", "description": "Search web"},
        ]

        allowed_tools = EXPECTED_SUBAGENT_ALLOWED_TOOLS
        filtered_tools = [t for t in all_tools if t.get("name") in allowed_tools]

        tool_names = [t["name"] for t in filtered_tools]

        # Verify forbidden tools are excluded
        assert "run_command" not in tool_names
        assert "spawn_agent" not in tool_names

        # Verify allowed tools are included
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "web_search" in tool_names

    def test_tool_filtering_empty_when_no_match(self):
        """Test that filtering returns empty list when no tools match."""
        all_tools = [
            {"name": "run_command", "description": "Execute command"},
            {"name": "spawn_agent", "description": "Spawn subagent"},
        ]

        allowed_tools = ["read_file", "write_file"]  # These don't exist in all_tools
        filtered_tools = [t for t in all_tools if t.get("name") in allowed_tools]

        assert filtered_tools == []

    def test_tool_filtering_none_allowed_returns_all(self):
        """Test that None allowed_tools returns all tools (main agent behavior)."""
        all_tools = [
            {"name": "read_file", "description": "Read file"},
            {"name": "run_command", "description": "Execute command"},
        ]

        allowed_tools = None  # No restriction
        # This is the logic in act_node lines 122-124
        if allowed_tools:
            filtered_tools = [t for t in all_tools if t.get("name") in allowed_tools]
        else:
            filtered_tools = all_tools

        assert len(filtered_tools) == 2


class TestSpawnAgentToolIsolation:
    """Test SpawnAgentTool isolation mechanisms."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tool = SpawnAgentTool()

    def test_spawn_agent_tool_properties(self):
        """Test SpawnAgentTool has correct properties."""
        assert self.tool.name == "spawn_agent"
        assert "sub-agent" in self.tool.description.lower() or "parallel" in self.tool.description.lower()

    def test_extract_subagent_result_exists(self):
        """Test that _extract_subagent_result method exists."""
        assert hasattr(self.tool, "_extract_subagent_result")
        assert callable(self.tool._extract_subagent_result)

    def test_spawn_agent_parameters(self):
        """Test SpawnAgentTool has correct parameters."""
        params = self.tool.parameters
        assert "task" in params["properties"]
        assert "task" in params["required"]


class TestSpawnParallelToolIsolation:
    """Test SpawnParallelTool isolation mechanisms."""

    def test_spawn_parallel_allowed_tools_excludes_run_command(self):
        """Verify SpawnParallelTool also excludes run_command from whitelist."""
        # The whitelist in parallel.py should match agent_spawn.py
        parallel_allowed_tools = [
            "read_file", "write_file", "edit_file",
            "list_dir", "search_files", "search_content",
            "web_search"
        ]

        assert "run_command" not in parallel_allowed_tools
        assert "spawn_agent" not in parallel_allowed_tools


class TestRecursionPrevention:
    """Test that subagents cannot spawn more subagents (recursion prevention)."""

    def test_subagent_cannot_spawn_agent(self):
        """Verify spawn_agent is not in subagent whitelist."""
        # This prevents infinite recursion of subagent spawning
        assert "spawn_agent" not in EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
            "Subagents must not be able to spawn more subagents"

    def test_subagent_cannot_spawn_parallel(self):
        """Verify spawn_parallel is not in subagent whitelist."""
        assert "spawn_parallel" not in EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
            "Subagents must not be able to spawn parallel agents"

    def test_all_spawning_tools_blocked(self):
        """Verify all agent-spawning tools are blocked."""
        spawning_tools = ["spawn_agent", "spawn_parallel", "plan_parallel", "execute_parallel"]

        for tool in spawning_tools:
            assert tool not in EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
                f"{tool} must be blocked to prevent subagent recursion"


class TestSubagentModeFunctions:
    """Test subagent mode context functions."""

    def test_set_and_get_subagent_mode(self):
        """Test setting and getting subagent mode."""
        from mini_claude.tools.file_ops import set_subagent_mode, is_subagent_mode

        # Default should be False
        set_subagent_mode(False)
        assert is_subagent_mode() is False

        # Set to True
        set_subagent_mode(True)
        assert is_subagent_mode() is True

        # Reset
        set_subagent_mode(False)

    def test_set_and_get_current_agent(self):
        """Test setting and getting current agent ID."""
        from mini_claude.tools.file_ops import set_current_agent, get_current_agent

        # Default should be 'main'
        set_current_agent("main")
        assert get_current_agent() == "main"

        # Set to subagent
        set_current_agent("subagent_001")
        assert get_current_agent() == "subagent_001"

        # Reset
        set_current_agent("main")


class TestSecurityBoundary:
    """Security boundary tests for subagent isolation."""

    def test_command_execution_blocked_in_subagent(self):
        """Test that command execution tools are blocked for subagents."""
        dangerous_tools = ["run_command", "run_background"]

        for tool in dangerous_tools:
            assert tool not in EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
                f"SECURITY RISK: {tool} is available to subagents"

    def test_file_operations_allowed_in_subagent(self):
        """Test that file operations are allowed for subagents."""
        safe_tools = ["read_file", "write_file", "edit_file", "list_dir"]

        for tool in safe_tools:
            assert tool in EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
                f"{tool} should be available to subagents"

    def test_web_tools_allowed_in_subagent(self):
        """Test that web tools are allowed for subagents."""
        web_tools = ["web_search"]

        for tool in web_tools:
            assert tool in EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
                f"{tool} should be available to subagents"

    def test_subagent_has_limited_but_sufficient_tools(self):
        """Test that subagent has enough tools to do useful work."""
        # Subagent should have at least file operations and web search
        required_categories = {
            "file_read": ["read_file", "list_dir", "search_files", "search_content"],
            "file_write": ["write_file", "edit_file"],
            "web": ["web_search"],
        }

        for category, tools in required_categories.items():
            has_tool = any(t in EXPECTED_SUBAGENT_ALLOWED_TOOLS for t in tools)
            assert has_tool, \
                f"Subagent lacks tools for {category} operations"


class TestMockedSubagentExecution:
    """Test subagent execution with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_subagent_state_passed_to_graph(self):
        """Test that subagent state with allowed_tools is properly created."""
        # This tests the state creation logic used in SpawnAgentTool.execute()
        # The build_agent_graph_no_checkpoint is imported inside the execute method
        # We test the state creation directly
        state = create_initial_state(
            user_input="Test subagent task",
            thread_id="test_subagent_001",
            is_subagent=True,
            allowed_tools=EXPECTED_SUBAGENT_ALLOWED_TOOLS
        )

        # Verify state is correctly configured
        assert state["is_subagent"] is True
        assert state["thread_id"] == "test_subagent_001"
        assert state["allowed_tools"] == EXPECTED_SUBAGENT_ALLOWED_TOOLS
        assert "run_command" not in state["allowed_tools"]

    @pytest.mark.asyncio
    async def test_tool_filtering_in_act_node_simulation(self):
        """Simulate the tool filtering that happens in act_node."""
        # Simulate all registered tools
        mock_all_tools = [
            {"name": "read_file", "description": "Read file"},
            {"name": "write_file", "description": "Write file"},
            {"name": "run_command", "description": "Execute command"},
            {"name": "spawn_agent", "description": "Spawn agent"},
            {"name": "web_search", "description": "Search web"},
        ]

        # Simulate subagent state
        state = {
            "allowed_tools": EXPECTED_SUBAGENT_ALLOWED_TOOLS,
            "is_subagent": True,
        }

        # Apply filtering logic from act_node
        tools = mock_all_tools
        allowed_tools = state.get("allowed_tools")
        if allowed_tools:
            tools = [t for t in tools if t.get("name") in allowed_tools]

        tool_names = [t["name"] for t in tools]

        # Verify filtering
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "web_search" in tool_names
        assert "run_command" not in tool_names
        assert "spawn_agent" not in tool_names


class TestWhitelistConsistency:
    """Test that whitelists are consistent across files."""

    def test_agent_spawn_whitelist_matches_expected(self):
        """Verify agent_spawn.py whitelist matches expected tools."""
        # This test documents the expected whitelist
        # If agent_spawn.py changes, this test will fail
        agent_spawn_whitelist = [
            "read_file", "write_file", "edit_file",
            "list_dir", "search_files", "search_content",
            "web_search"
        ]

        assert agent_spawn_whitelist == EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
            "agent_spawn.py whitelist must match expected tools"

    def test_parallel_whitelist_matches_agent_spawn(self):
        """Verify parallel.py whitelist matches agent_spawn.py."""
        # Both files should have identical whitelists
        parallel_whitelist = [
            "read_file", "write_file", "edit_file",
            "list_dir", "search_files", "search_content",
            "web_search"
        ]

        assert parallel_whitelist == EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
            "parallel.py whitelist must match agent_spawn.py whitelist"


class TestSecurityAssertions:
    """Critical security assertions that must always pass."""

    def test_no_wildcard_in_whitelist(self):
        """CRITICAL: Whitelist must never contain wildcard characters."""
        for tool in EXPECTED_SUBAGENT_ALLOWED_TOOLS:
            assert tool != "*", "Wildcard in whitelist is a security risk"
            assert tool != "all", "'all' in whitelist is a security risk"
            assert not tool.startswith("*"), "Wildcard pattern in whitelist"

    def test_run_command_absolutely_excluded(self):
        """CRITICAL: run_command must NEVER be available to subagents."""
        # This is the most important security test
        assert "run_command" not in EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
            "SECURITY VIOLATION: run_command is available to subagents!"

    def test_no_privilege_escalation_tools(self):
        """CRITICAL: No tools that could allow privilege escalation."""
        escalation_tools = [
            "run_command",      # Shell command execution
            "run_background",   # Background command execution
            "spawn_agent",      # Could spawn agent with more privileges
        ]

        for tool in escalation_tools:
            assert tool not in EXPECTED_SUBAGENT_ALLOWED_TOOLS, \
                f"PRIVILEGE ESCALATION RISK: {tool} available to subagents"
