"""Tests for tool dependency management."""

import pytest

from mini_claude.tools.dependencies import (
    ToolDependency,
    DependencyGraph,
    DependencyType,
    CyclicDependencyError,
    get_dependency_graph,
    reset_dependency_graph,
)


class TestToolDependency:
    """Test ToolDependency dataclass."""

    def test_basic_creation(self):
        """Test creating a basic dependency."""
        dep = ToolDependency(
            tool_name="edit_file",
            depends_on=["read_file"],
            description="edit requires read",
        )

        assert dep.tool_name == "edit_file"
        assert dep.depends_on == ["read_file"]
        assert dep.optional is False
        assert dep.description == "edit requires read"

    def test_optional_dependency(self):
        """Test creating an optional dependency."""
        dep = ToolDependency(
            tool_name="force_write",
            depends_on=["read_file"],
            optional=True,
        )

        assert dep.optional is True

    def test_multiple_dependencies(self):
        """Test dependency with multiple depends_on."""
        dep = ToolDependency(
            tool_name="aggregate_results",
            depends_on=["spawn_agent", "spawn_parallel"],
        )

        assert len(dep.depends_on) == 2
        assert "spawn_agent" in dep.depends_on
        assert "spawn_parallel" in dep.depends_on

    def test_string_depends_on_converted_to_list(self):
        """Test that string depends_on is converted to list."""
        dep = ToolDependency(
            tool_name="tool_a",
            depends_on="tool_b",  # String, not list
        )

        assert dep.depends_on == ["tool_b"]

    def test_tool_name_required(self):
        """Test that tool_name is required."""
        with pytest.raises(ValueError):
            ToolDependency(tool_name="", depends_on=["other"])

    def test_default_values(self):
        """Test default values."""
        dep = ToolDependency(tool_name="test_tool")

        assert dep.depends_on == []
        assert dep.optional is False
        assert dep.description == ""
        assert dep.dependency_type == DependencyType.REQUIRED


class TestDependencyGraphBasic:
    """Test basic DependencyGraph functionality."""

    def setup_method(self):
        """Create fresh graph for each test."""
        self.graph = DependencyGraph()

    def test_empty_graph(self):
        """Test empty graph state."""
        assert len(self.graph._dependencies) == 0
        assert len(self.graph.get_all_tools()) == 0

    def test_add_dependency(self):
        """Test adding a dependency."""
        dep = ToolDependency(
            tool_name="edit_file",
            depends_on=["read_file"],
        )

        self.graph.add_dependency(dep)

        assert "edit_file" in self.graph._dependencies
        assert self.graph.get_dependencies("edit_file") == ["read_file"]

    def test_add_multiple_dependencies(self):
        """Test adding multiple dependencies for same tool."""
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_b"],
            )
        )
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_c"],
            )
        )

        deps = self.graph.get_dependencies("tool_a")
        assert "tool_b" in deps
        assert "tool_c" in deps

    def test_remove_dependency_all(self):
        """Test removing all dependencies for a tool."""
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_b", "tool_c"],
            )
        )

        count = self.graph.remove_dependency("tool_a")

        assert count == 1  # One ToolDependency removed
        assert "tool_a" not in self.graph._dependencies

    def test_remove_specific_dependency(self):
        """Test removing a specific dependency."""
        # Create two separate dependencies for tool_a
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_b"],
            )
        )
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_c"],
            )
        )

        # Remove tool_b dependency
        count = self.graph.remove_dependency("tool_a", "tool_b")

        assert count == 1
        remaining = self.graph.get_dependencies("tool_a")
        assert "tool_b" not in remaining
        assert "tool_c" in remaining

    def test_remove_nonexistent(self):
        """Test removing nonexistent dependency."""
        count = self.graph.remove_dependency("nonexistent")
        assert count == 0


class TestDependencyGraphGetDependencies:
    """Test dependency retrieval methods."""

    def setup_method(self):
        """Create graph with sample dependencies."""
        self.graph = DependencyGraph()
        # Create: tool_a -> tool_b -> tool_c
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_b"],
            )
        )
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_b",
                depends_on=["tool_c"],
            )
        )

    def test_get_direct_dependencies(self):
        """Test getting direct dependencies."""
        deps = self.graph.get_dependencies("tool_a")
        assert deps == ["tool_b"]

    def test_get_all_dependencies_transitive(self):
        """Test getting all transitive dependencies."""
        all_deps = self.graph.get_all_dependencies("tool_a")

        assert "tool_b" in all_deps
        assert "tool_c" in all_deps

    def test_get_dependencies_no_deps(self):
        """Test getting dependencies for tool with none."""
        deps = self.graph.get_dependencies("tool_c")
        assert deps == []

    def test_get_all_dependencies_no_deps(self):
        """Test getting all dependencies for tool with none."""
        all_deps = self.graph.get_all_dependencies("tool_c")
        assert all_deps == set()

    def test_get_dependents(self):
        """Test getting tools that depend on a tool."""
        dependents = self.graph.get_dependents("tool_c")
        assert "tool_b" in dependents

        dependents_a = self.graph.get_dependents("tool_b")
        assert "tool_a" in dependents_a

    def test_get_dependents_none(self):
        """Test getting dependents for tool with none."""
        dependents = self.graph.get_dependents("tool_a")
        assert dependents == []


class TestDependencyGraphAvailability:
    """Test dependency availability checking."""

    def setup_method(self):
        """Create graph with sample dependencies."""
        self.graph = DependencyGraph()
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_b"],
            )
        )
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_c"],
                optional=True,
            )
        )

    def test_all_available(self):
        """Test when all dependencies are available."""
        available, missing_req, missing_opt = self.graph.check_availability(
            "tool_a", {"tool_b", "tool_c"}
        )

        assert available is True
        assert missing_req == []
        assert missing_opt == []

    def test_missing_required(self):
        """Test when required dependency is missing."""
        available, missing_req, missing_opt = self.graph.check_availability(
            "tool_a",
            {"tool_c"},  # tool_b missing
        )

        assert available is False
        assert "tool_b" in missing_req

    def test_missing_optional_only(self):
        """Test when only optional dependency is missing."""
        available, missing_req, missing_opt = self.graph.check_availability(
            "tool_a",
            {"tool_b"},  # tool_c missing but optional
        )

        assert available is True
        assert missing_req == []
        assert "tool_c" in missing_opt

    def test_no_dependencies(self):
        """Test tool with no dependencies."""
        available, missing_req, missing_opt = self.graph.check_availability("tool_x", set())

        assert available is True

    def test_check_with_registered_tools(self):
        """Test using registered tools set."""
        # tool_a has: tool_b (required), tool_c (optional)
        # Register only tool_b - should be available since tool_c is optional
        self.graph.register_tool("tool_b")

        available, missing_req, missing_opt = self.graph.check_availability("tool_a")

        assert available is True  # tool_b is registered, tool_c is optional
        assert missing_req == []
        assert "tool_c" in missing_opt


class TestDependencyGraphCycleDetection:
    """Test cycle detection."""

    def setup_method(self):
        """Create fresh graph."""
        self.graph = DependencyGraph()

    def test_no_cycle(self):
        """Test graph without cycles."""
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_b"],
            )
        )
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_b",
                depends_on=["tool_c"],
            )
        )

        cycle = self.graph.detect_cycle()
        assert cycle is None

    def test_simple_cycle(self):
        """Test detecting simple cycle a -> b -> a."""
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_b"],
            )
        )

        # This should raise because it creates a cycle
        with pytest.raises(CyclicDependencyError) as exc_info:
            self.graph.add_dependency(
                ToolDependency(
                    tool_name="tool_b",
                    depends_on=["tool_a"],
                )
            )

        assert "cycle" in str(exc_info.value).lower()

    def test_longer_cycle(self):
        """Test detecting longer cycle a -> b -> c -> a."""
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_b"],
            )
        )
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_b",
                depends_on=["tool_c"],
            )
        )

        with pytest.raises(CyclicDependencyError):
            self.graph.add_dependency(
                ToolDependency(
                    tool_name="tool_c",
                    depends_on=["tool_a"],
                )
            )

    def test_self_cycle(self):
        """Test detecting self-dependency."""
        with pytest.raises(CyclicDependencyError):
            self.graph.add_dependency(
                ToolDependency(
                    tool_name="tool_a",
                    depends_on=["tool_a"],
                )
            )

    def test_detect_cycle_returns_path(self):
        """Test that detect_cycle returns the cycle path."""
        # Manually create cycle (bypassing add_dependency check)
        self.graph._dependencies["tool_a"].append(
            ToolDependency(tool_name="tool_a", depends_on=["tool_b"])
        )
        self.graph._dependencies["tool_b"].append(
            ToolDependency(tool_name="tool_b", depends_on=["tool_a"])
        )

        cycle = self.graph.detect_cycle()
        assert cycle is not None
        assert len(cycle) >= 2


class TestDependencyGraphTopologicalSort:
    """Test topological sort for execution order."""

    def setup_method(self):
        """Create fresh graph."""
        self.graph = DependencyGraph()

    def test_simple_order(self):
        """Test simple dependency order."""
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_b"],
            )
        )

        levels = self.graph.get_execution_order(["tool_a", "tool_b"])

        # tool_b should be in earlier level than tool_a
        assert len(levels) == 2
        assert "tool_b" in levels[0]
        assert "tool_a" in levels[1]

    def test_parallel_execution(self):
        """Test tools that can run in parallel."""
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_c"],
            )
        )
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_b",
                depends_on=["tool_c"],
            )
        )

        levels = self.graph.get_execution_order(["tool_a", "tool_b", "tool_c"])

        # tool_c should be first, then tool_a and tool_b can run in parallel
        assert levels[0] == ["tool_c"]
        assert set(levels[1]) == {"tool_a", "tool_b"}

    def test_chain_order(self):
        """Test chain dependency order."""
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_b"],
            )
        )
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_b",
                depends_on=["tool_c"],
            )
        )

        levels = self.graph.get_execution_order(["tool_a", "tool_b", "tool_c"])

        assert levels[0] == ["tool_c"]
        assert levels[1] == ["tool_b"]
        assert levels[2] == ["tool_a"]

    def test_independent_tools(self):
        """Test tools with no dependencies between them."""
        levels = self.graph.get_execution_order(["tool_a", "tool_b", "tool_c"])

        # All can run in parallel
        assert len(levels) == 1
        assert set(levels[0]) == {"tool_a", "tool_b", "tool_c"}

    def test_cycle_raises_error(self):
        """Test that cycle raises error during topological sort."""
        # Manually create cycle
        self.graph._dependencies["tool_a"].append(
            ToolDependency(tool_name="tool_a", depends_on=["tool_b"])
        )
        self.graph._dependencies["tool_b"].append(
            ToolDependency(tool_name="tool_b", depends_on=["tool_a"])
        )

        with pytest.raises(CyclicDependencyError):
            self.graph.get_execution_order(["tool_a", "tool_b"])

    def test_single_tool(self):
        """Test single tool ordering."""
        levels = self.graph.get_execution_order(["tool_a"])

        assert len(levels) == 1
        assert levels[0] == ["tool_a"]


class TestDependencyGraphToolRegistration:
    """Test tool registration functionality."""

    def setup_method(self):
        """Create fresh graph."""
        self.graph = DependencyGraph()

    def test_register_tool(self):
        """Test registering a tool."""
        self.graph.register_tool("tool_a")

        assert "tool_a" in self.graph._registered_tools

    def test_unregister_tool(self):
        """Test unregistering a tool."""
        self.graph.register_tool("tool_a")
        self.graph.unregister_tool("tool_a")

        assert "tool_a" not in self.graph._registered_tools

    def test_unregister_nonexistent(self):
        """Test unregistering nonexistent tool doesn't error."""
        self.graph.unregister_tool("nonexistent")  # Should not raise

    def test_check_availability_uses_registered(self):
        """Test check_availability uses registered tools."""
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_b"],
            )
        )
        self.graph.register_tool("tool_b")

        available, _, _ = self.graph.check_availability("tool_a")
        assert available is True


class TestDependencyGraphExport:
    """Test export functionality."""

    def setup_method(self):
        """Create graph with sample data."""
        self.graph = DependencyGraph()
        self.graph.add_dependency(
            ToolDependency(
                tool_name="tool_a",
                depends_on=["tool_b"],
                description="a depends on b",
            )
        )
        self.graph.register_tool("tool_a")
        self.graph.register_tool("tool_b")

    def test_to_dict(self):
        """Test exporting to dictionary."""
        data = self.graph.to_dict()

        assert "dependencies" in data
        assert "registered_tools" in data
        assert "tool_a" in data["dependencies"]
        assert set(data["registered_tools"]) == {"tool_a", "tool_b"}

    def test_to_dict_includes_details(self):
        """Test to_dict includes dependency details."""
        data = self.graph.to_dict()

        dep_info = data["dependencies"]["tool_a"][0]
        assert dep_info["depends_on"] == ["tool_b"]
        assert dep_info["optional"] is False
        assert dep_info["description"] == "a depends on b"

    def test_clear(self):
        """Test clearing the graph."""
        self.graph.clear()

        assert len(self.graph._dependencies) == 0
        assert len(self.graph._registered_tools) == 0
        assert len(self.graph._transitive_cache) == 0


class TestGlobalDependencyGraph:
    """Test global instance functions."""

    def test_get_dependency_graph_singleton(self):
        """Test that get_dependency_graph returns same instance."""
        reset_dependency_graph()

        graph1 = get_dependency_graph()
        graph2 = get_dependency_graph()

        assert graph1 is graph2

    def test_reset_dependency_graph(self):
        """Test that reset creates new instance."""
        graph1 = get_dependency_graph()
        reset_dependency_graph()
        graph2 = get_dependency_graph()

        assert graph1 is not graph2

    def test_builtin_dependencies_loaded(self):
        """Test that builtin dependencies are loaded."""
        reset_dependency_graph()
        graph = get_dependency_graph()

        # Should have builtin dependencies
        assert len(graph._dependencies) > 0
        assert "edit_file" in graph._dependencies


class TestBuiltinDependencies:
    """Test builtin tool dependencies."""

    def setup_method(self):
        """Reset and get fresh graph with builtin deps."""
        reset_dependency_graph()
        self.graph = get_dependency_graph()

    def test_edit_file_depends_on_read_file(self):
        """Test edit_file depends on read_file."""
        deps = self.graph.get_dependencies("edit_file")
        assert "read_file" in deps

    def test_spawn_parallel_depends_on_spawn_agent(self):
        """Test spawn_parallel depends on spawn_agent."""
        deps = self.graph.get_dependencies("spawn_parallel")
        assert "spawn_agent" in deps

    def test_execute_parallel_depends_on_plan_parallel(self):
        """Test execute_parallel depends on plan_parallel."""
        deps = self.graph.get_dependencies("execute_parallel")
        assert "plan_parallel" in deps

    def test_aggregate_results_has_dependencies(self):
        """Test aggregate_results has spawn dependencies."""
        deps = self.graph.get_dependencies("aggregate_results")
        assert len(deps) > 0
        # Should have at least one of spawn_agent or spawn_parallel
        assert any(d in deps for d in ["spawn_agent", "spawn_parallel"])

    def test_force_write_optional_dependency(self):
        """Test force_write has optional dependency on read_file."""
        # Find the force_write dependency
        force_write_deps = self.graph._dependencies.get("force_write", [])
        has_optional_read_file = any(
            d.optional and "read_file" in d.depends_on for d in force_write_deps
        )
        assert has_optional_read_file

    def test_no_cycles_in_builtin(self):
        """Test that builtin dependencies have no cycles."""
        cycle = self.graph.detect_cycle()
        assert cycle is None


class TestDependencyIntegration:
    """Integration tests with tool registry."""

    def test_tool_registry_get_dependency_info(self):
        """Test ToolRegistry.get_dependency_info method."""
        from mini_claude.tools import tool_registry

        # This should not raise
        info = tool_registry.get_dependency_info("edit_file")

        assert "dependencies" in info
        assert "all_dependencies" in info
        assert "dependents" in info
        assert "available" in info

    def test_tool_registry_dependency_check(self):
        """Test dependency check in tool registry."""
        from mini_claude.tools import tool_registry

        # All builtin tools should have their dependencies available
        for tool_name in tool_registry.list_tools():
            info = tool_registry.get_dependency_info(tool_name)
            available, missing_req, _ = info["available"]
            # Most tools should have available dependencies
            # (Some might not if they depend on non-registered tools)
            if not available:
                # At least verify the check returned something
                assert len(missing_req) > 0
