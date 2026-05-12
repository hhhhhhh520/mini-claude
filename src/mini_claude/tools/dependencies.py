"""Tool dependency management.

Provides dependency graph for tools with:
- Dependency declaration and tracking
- Topological sort for execution order
- Cycle detection
- Availability checking
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple
from enum import Enum
from collections import defaultdict

from ..utils.logger import get_logger

logger = get_logger("mini_claude.tools.dependencies")


class DependencyType(Enum):
    """Type of dependency relationship."""

    REQUIRED = "required"  # Must be satisfied for tool to work
    OPTIONAL = "optional"  # Nice to have, tool can work without it
    CONFLICT = "conflict"  # Cannot be used together


@dataclass
class ToolDependency:
    """Dependency definition for a tool.

    Attributes:
        tool_name: Name of the tool that has dependencies
        depends_on: List of tool names this tool depends on
        optional: Whether this dependency is optional
        description: Human-readable explanation of why dependency exists
        dependency_type: Type of dependency relationship
    """

    tool_name: str
    depends_on: List[str] = field(default_factory=list)
    optional: bool = False
    description: str = ""
    dependency_type: DependencyType = DependencyType.REQUIRED

    def __post_init__(self):
        """Validate dependency definition."""
        if not self.tool_name:
            raise ValueError("tool_name is required")

        # Convert single string to list
        if isinstance(self.depends_on, str):
            self.depends_on = [self.depends_on]


class CyclicDependencyError(Exception):
    """Raised when a cycle is detected in the dependency graph."""

    pass


class DependencyGraph:
    """Manages tool dependencies with cycle detection and topological sort.

    Example:
        >>> graph = DependencyGraph()
        >>> graph.add_dependency(ToolDependency(
        ...     tool_name="edit_file",
        ...     depends_on=["read_file"],
        ...     description="edit_file requires reading file first"
        ... ))
        >>> graph.get_dependencies("edit_file")
        ['read_file']
    """

    def __init__(self):
        """Initialize empty dependency graph."""
        # tool_name -> list of ToolDependency
        self._dependencies: Dict[str, List[ToolDependency]] = defaultdict(list)
        # Cache for computed transitive dependencies
        self._transitive_cache: Dict[str, Set[str]] = {}
        # Track registered tools (populated from registry)
        self._registered_tools: Set[str] = set()

    def add_dependency(self, dependency: ToolDependency) -> None:
        """Add a dependency to the graph.

        Args:
            dependency: ToolDependency to add

        Raises:
            CyclicDependencyError: If adding this creates a cycle
        """
        tool = dependency.tool_name

        # Clear cache when adding new dependency
        if tool in self._transitive_cache:
            del self._transitive_cache[tool]

        self._dependencies[tool].append(dependency)

        # Check for cycles after adding
        cycle = self.detect_cycle()
        if cycle:
            # Remove the dependency we just added
            self._dependencies[tool].pop()
            raise CyclicDependencyError(
                f"Adding dependency '{tool} -> {dependency.depends_on}' "
                f"would create cycle: {' -> '.join(cycle)}"
            )

        logger.debug(
            "Dependency added",
            tool=tool,
            depends_on=dependency.depends_on,
            optional=dependency.optional,
        )

    def remove_dependency(self, tool_name: str, depends_on: str = None) -> int:
        """Remove dependencies for a tool.

        Args:
            tool_name: Tool to remove dependencies from
            depends_on: Specific dependency to remove (if None, removes all)

        Returns:
            Number of dependencies removed
        """
        if tool_name not in self._dependencies:
            return 0

        if depends_on is None:
            # Remove all dependencies
            count = len(self._dependencies[tool_name])
            del self._dependencies[tool_name]
            self._transitive_cache.pop(tool_name, None)
            return count

        # Remove specific dependency
        original_len = len(self._dependencies[tool_name])
        self._dependencies[tool_name] = [
            d for d in self._dependencies[tool_name] if depends_on not in d.depends_on
        ]
        removed = original_len - len(self._dependencies[tool_name])

        if removed > 0:
            self._transitive_cache.pop(tool_name, None)

        return removed

    def get_dependencies(self, tool_name: str) -> List[str]:
        """Get direct dependencies of a tool.

        Args:
            tool_name: Tool to get dependencies for

        Returns:
            List of tool names this tool depends on directly
        """
        if tool_name not in self._dependencies:
            return []

        result = []
        for dep in self._dependencies[tool_name]:
            result.extend(dep.depends_on)

        return list(set(result))  # Deduplicate

    def get_all_dependencies(self, tool_name: str) -> Set[str]:
        """Get all dependencies of a tool (transitive closure).

        Args:
            tool_name: Tool to get all dependencies for

        Returns:
            Set of all tool names this tool depends on (directly and indirectly)
        """
        # Check cache
        if tool_name in self._transitive_cache:
            return self._transitive_cache[tool_name].copy()

        result = set()
        to_visit = list(self.get_dependencies(tool_name))

        while to_visit:
            dep = to_visit.pop()
            if dep not in result:
                result.add(dep)
                to_visit.extend(self.get_dependencies(dep))

        # Cache result
        self._transitive_cache[tool_name] = result
        return result.copy()

    def get_dependents(self, tool_name: str) -> List[str]:
        """Get tools that depend on this tool.

        Args:
            tool_name: Tool to find dependents for

        Returns:
            List of tool names that depend on this tool
        """
        dependents = []
        for tool, deps in self._dependencies.items():
            for dep in deps:
                if tool_name in dep.depends_on:
                    dependents.append(tool)
                    break

        return list(set(dependents))

    def check_availability(
        self, tool_name: str, available_tools: Set[str] = None
    ) -> Tuple[bool, List[str], List[str]]:
        """Check if all required dependencies are available.

        Args:
            tool_name: Tool to check
            available_tools: Set of available tool names (uses registry if None)

        Returns:
            Tuple of (is_available, missing_required, missing_optional)
        """
        if available_tools is None:
            available_tools = self._registered_tools

        if tool_name not in self._dependencies:
            return True, [], []

        missing_required = []
        missing_optional = []

        for dep in self._dependencies[tool_name]:
            for required_tool in dep.depends_on:
                if required_tool not in available_tools:
                    if dep.optional:
                        missing_optional.append(required_tool)
                    else:
                        missing_required.append(required_tool)

        is_available = len(missing_required) == 0
        return is_available, missing_required, missing_optional

    def get_execution_order(self, tools: List[str]) -> List[List[str]]:
        """Get execution order using topological sort.

        Args:
            tools: List of tool names to order

        Returns:
            List of levels, where each level contains tools that can be
            executed in parallel (no dependencies between them in that level)

        Raises:
            CyclicDependencyError: If there's a cycle in the dependencies
            ValueError: If a tool has unresolvable dependencies
        """
        # Check for cycles first
        cycle = self.detect_cycle()
        if cycle:
            raise CyclicDependencyError(
                f"Cannot compute execution order: cycle detected: {' -> '.join(cycle)}"
            )

        # Build in-degree map for topological sort (Kahn's algorithm)
        in_degree: Dict[str, int] = {t: 0 for t in tools}
        dep_graph: Dict[str, Set[str]] = {t: set() for t in tools}

        # Build dependency graph for requested tools only
        for tool in tools:
            deps = self.get_dependencies(tool)
            for dep in deps:
                if dep in tools:
                    dep_graph[tool].add(dep)

        # Calculate in-degrees
        for tool in tools:
            for dep in dep_graph[tool]:
                in_degree[dep] = in_degree.get(dep, 0) + 1

        # Wait, we need reverse: tool depends on dep, so dep should come first
        # Let's recalculate
        in_degree = {t: 0 for t in tools}
        reverse_graph: Dict[str, Set[str]] = {t: set() for t in tools}

        for tool in tools:
            deps = self.get_dependencies(tool)
            for dep in deps:
                if dep in tools:
                    reverse_graph[dep].add(tool)  # dep -> tool
                    in_degree[tool] += 1

        # Kahn's algorithm
        levels = []
        remaining = set(tools)

        while remaining:
            # Find all tools with in-degree 0
            current_level = [t for t in remaining if in_degree[t] == 0]

            if not current_level:
                # This shouldn't happen if we checked for cycles
                remaining_tools = list(remaining)
                raise CyclicDependencyError(f"Unexpected cycle detected among: {remaining_tools}")

            levels.append(sorted(current_level))  # Sort for deterministic output

            # Remove current level and update in-degrees
            for tool in current_level:
                remaining.remove(tool)
                for dependent in reverse_graph[tool]:
                    in_degree[dependent] -= 1

        return levels

    def detect_cycle(self) -> Optional[List[str]]:
        """Detect if there's a cycle in the dependency graph.

        Uses DFS with coloring:
        - White (0): Not visited
        - Gray (1): Being processed (in current path)
        - Black (2): Fully processed

        Returns:
            List representing the cycle if found, None otherwise
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = defaultdict(int)

        # Get all tools in the graph
        all_tools = set(self._dependencies.keys())
        for deps in self._dependencies.values():
            for dep in deps:
                all_tools.update(dep.depends_on)

        def dfs(node: str, path: List[str]) -> Optional[List[str]]:
            """DFS helper that returns cycle path if found."""
            if color[node] == GRAY:
                # Found a cycle - return the cycle path
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]

            if color[node] == BLACK:
                return None

            color[node] = GRAY
            path.append(node)

            for dep in self.get_dependencies(node):
                cycle = dfs(dep, path)
                if cycle:
                    return cycle

            path.pop()
            color[node] = BLACK
            return None

        for tool in all_tools:
            if color[tool] == WHITE:
                cycle = dfs(tool, [])
                if cycle:
                    return cycle

        return None

    def register_tool(self, tool_name: str) -> None:
        """Register a tool as available.

        Args:
            tool_name: Name of the tool to register
        """
        self._registered_tools.add(tool_name)

    def unregister_tool(self, tool_name: str) -> None:
        """Unregister a tool.

        Args:
            tool_name: Name of the tool to unregister
        """
        self._registered_tools.discard(tool_name)

    def get_all_tools(self) -> Set[str]:
        """Get all tools in the dependency graph.

        Returns:
            Set of all tool names that have dependencies or are depended upon
        """
        all_tools = set(self._dependencies.keys())
        for deps in self._dependencies.values():
            for dep in deps:
                all_tools.update(dep.depends_on)
        return all_tools

    def to_dict(self) -> Dict:
        """Export dependency graph as dictionary.

        Returns:
            Dictionary representation of the graph
        """
        result = {
            "dependencies": {},
            "registered_tools": list(self._registered_tools),
        }

        for tool, deps in self._dependencies.items():
            result["dependencies"][tool] = [
                {
                    "depends_on": d.depends_on,
                    "optional": d.optional,
                    "description": d.description,
                    "type": d.dependency_type.value,
                }
                for d in deps
            ]

        return result

    def clear(self) -> None:
        """Clear all dependencies."""
        self._dependencies.clear()
        self._transitive_cache.clear()
        self._registered_tools.clear()


# Global dependency graph instance
_dependency_graph: Optional[DependencyGraph] = None


def get_dependency_graph() -> DependencyGraph:
    """Get the global dependency graph instance.

    This function provides backward compatibility with existing code.
    New code should prefer ApplicationContext.dependency_graph.

    Returns:
        Global DependencyGraph instance
    """
    global _dependency_graph
    if _dependency_graph is None:
        # Try to use ApplicationContext first
        try:
            from mini_claude.context import get_context

            ctx = get_context()
            if ctx._dependency_graph.is_initialized():
                _dependency_graph = ctx.dependency_graph
            else:
                _dependency_graph = DependencyGraph()
                _init_builtin_dependencies()
                ctx.dependency_graph = _dependency_graph
        except ImportError:
            _dependency_graph = DependencyGraph()
            _init_builtin_dependencies()
    return _dependency_graph


def reset_dependency_graph() -> None:
    """Reset the global dependency graph."""
    global _dependency_graph
    _dependency_graph = None
    # Also reset in context
    try:
        from mini_claude.context import get_context

        ctx = get_context()
        ctx._dependency_graph.reset()
    except ImportError:
        pass


def _init_builtin_dependencies() -> None:
    """Initialize builtin tool dependencies.

    Defines the default dependency relationships between core tools.
    """
    graph = get_dependency_graph()

    # edit_file depends on read_file (need to read before editing)
    graph.add_dependency(
        ToolDependency(
            tool_name="edit_file",
            depends_on=["read_file"],
            optional=False,
            description="edit_file requires reading file content first to find text to replace",
        )
    )

    # force_write optionally depends on read_file (for conflict detection context)
    graph.add_dependency(
        ToolDependency(
            tool_name="force_write",
            depends_on=["read_file"],
            optional=True,
            description="read_file helps detect conflicts but force_write can work without it",
        )
    )

    # spawn_parallel depends on spawn_agent (parallel uses agent spawning)
    graph.add_dependency(
        ToolDependency(
            tool_name="spawn_parallel",
            depends_on=["spawn_agent"],
            optional=False,
            description="spawn_parallel uses spawn_agent internally for parallel task execution",
        )
    )

    # aggregate_results depends on spawn_agent or spawn_parallel (need agents to aggregate)
    graph.add_dependency(
        ToolDependency(
            tool_name="aggregate_results",
            depends_on=["spawn_agent", "spawn_parallel"],
            optional=False,
            description="aggregate_results collects results from spawned agents",
        )
    )

    # execute_parallel depends on plan_parallel (must plan before execute)
    graph.add_dependency(
        ToolDependency(
            tool_name="execute_parallel",
            depends_on=["plan_parallel"],
            optional=False,
            description="execute_parallel requires a plan from plan_parallel first",
        )
    )

    logger.debug("Builtin dependencies initialized", count=len(graph._dependencies))
