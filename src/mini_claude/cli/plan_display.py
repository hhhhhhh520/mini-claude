"""Execution plan visualization for CLI.

This module provides PlanVisualizer to display execution plans,
progress updates, and summaries using Rich library.

Display Formats:
- Tree format: Shows hierarchical plan structure with dependencies
- List format: Simple numbered list of steps
- Progress format: Real-time step status updates
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from mini_claude.agent.complexity import ComplexityLevel, ComplexityResult
from mini_claude.utils.logger import get_logger

logger = get_logger(__name__)


class StepStatus(str, Enum):
    """Status of an execution step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class DisplayFormat(str, Enum):
    """Display format options."""

    TREE = "tree"
    LIST = "list"
    COMPACT = "compact"


@dataclass
class PlanStep:
    """A step in the execution plan.

    Attributes:
        id: Unique step identifier
        description: Step description
        status: Current status
        dependencies: List of step IDs this step depends on
        details: Additional step details
    """

    id: str
    description: str
    status: StepStatus = StepStatus.PENDING
    dependencies: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """Complete execution plan.

    Attributes:
        steps: List of plan steps
        total_steps: Total number of steps
        strategy: Execution strategy
        estimated_time: Estimated execution time (seconds)
        complexity_score: Complexity score of the task
    """

    steps: List[PlanStep] = field(default_factory=list)
    total_steps: int = 0
    strategy: str = "react"
    estimated_time: float = 0.0
    complexity_score: int = 0

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        """Get a step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def update_step_status(self, step_id: str, status: StepStatus) -> bool:
        """Update status of a step."""
        step = self.get_step(step_id)
        if step:
            step.status = status
            return True
        return False


class PlanVisualizer:
    """Visualizes execution plans using Rich library.

    This class provides methods to display execution plans in various
    formats (tree, list, compact), show progress updates, and display
    execution summaries.

    Example:
        visualizer = PlanVisualizer()
        plan = ExecutionPlan(steps=[PlanStep("1", "Read file")])
        complexity = ComplexityResult(level=ComplexityLevel.SIMPLE, score=25, strategy="react")
        visualizer.display_plan(plan, complexity)
    """

    # Status color mapping
    STATUS_COLORS: Dict[StepStatus, str] = {
        StepStatus.PENDING: "dim",
        StepStatus.RUNNING: "yellow",
        StepStatus.COMPLETED: "green",
        StepStatus.FAILED: "red",
        StepStatus.SKIPPED: "blue",
    }

    # Status icons
    STATUS_ICONS: Dict[StepStatus, str] = {
        StepStatus.PENDING: "[dim]○[/]",
        StepStatus.RUNNING: "[yellow]●[/]",
        StepStatus.COMPLETED: "[green]●[/]",
        StepStatus.FAILED: "[red]●[/]",
        StepStatus.SKIPPED: "[blue]○[/]",
    }

    # Complexity level colors
    LEVEL_COLORS: Dict[ComplexityLevel, str] = {
        ComplexityLevel.SIMPLE: "green",
        ComplexityLevel.MEDIUM: "yellow",
        ComplexityLevel.COMPLEX: "red",
    }

    def __init__(self, console: Optional[Console] = None):
        """Initialize the visualizer.

        Args:
            console: Rich Console instance (creates new if None)
        """
        self.console = console or Console()
        self._current_plan: Optional[ExecutionPlan] = None
        self._progress: Optional[Progress] = None

    def display_plan(
        self,
        plan: ExecutionPlan,
        complexity: ComplexityResult,
        format: DisplayFormat = DisplayFormat.TREE,
    ) -> None:
        """Display execution plan.

        Args:
            plan: Execution plan with steps and metadata
            complexity: Complexity analysis result
            format: Display format (tree, list, compact)
        """
        self._current_plan = plan

        # Choose display format based on complexity
        if complexity.level == ComplexityLevel.SIMPLE and format != DisplayFormat.COMPACT:
            # Simple tasks: use compact format by default
            self._display_compact_plan(plan, complexity)
        elif format == DisplayFormat.TREE:
            self._display_tree_plan(plan, complexity)
        elif format == DisplayFormat.LIST:
            self._display_list_plan(plan, complexity)
        else:
            self._display_compact_plan(plan, complexity)

        logger.debug(
            "Plan displayed",
            steps=plan.total_steps,
            format=format.value,
            complexity=complexity.level.value,
        )

    def display_progress(
        self, step_id: str, status: StepStatus, message: Optional[str] = None
    ) -> None:
        """Display execution progress for a step.

        Args:
            step_id: Step identifier
            status: New status
            message: Optional status message
        """
        if self._current_plan:
            self._current_plan.update_step_status(step_id, status)

        # Get step description
        step_desc = ""
        if self._current_plan:
            step = self._current_plan.get_step(step_id)
            if step:
                step_desc = step.description

        # Display status update
        icon = self.STATUS_ICONS.get(status, "○")
        color = self.STATUS_COLORS.get(status, "dim")

        if message:
            self.console.print(f"{icon} [{color}]{step_id}: {step_desc}[/] - {message}")
        else:
            self.console.print(f"{icon} [{color}]{step_id}: {step_desc}[/]")

    def display_summary(self, result: Dict[str, Any]) -> None:
        """Display execution summary.

        Args:
            result: Execution result containing:
                - success: Whether execution succeeded
                - total_steps: Total steps executed
                - completed_steps: Number of completed steps
                - failed_steps: Number of failed steps
                - execution_time: Execution time in seconds
                - errors: List of error messages
        """
        success = result.get("success", False)
        total_steps = result.get("total_steps", 0)
        completed_steps = result.get("completed_steps", 0)
        failed_steps = result.get("failed_steps", 0)
        execution_time = result.get("execution_time", 0.0)
        errors = result.get("errors", [])

        # Create summary table
        table = Table(title="Execution Summary", show_header=False, box=None)
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")

        # Status row
        status_text = "[green]SUCCESS[/]" if success else "[red]FAILED[/]"
        table.add_row("Status", status_text)

        # Steps row
        table.add_row("Steps", f"{completed_steps}/{total_steps} completed")

        # Failed steps row
        if failed_steps > 0:
            table.add_row("Failed", f"[red]{failed_steps}[/]")

        # Time row
        table.add_row("Time", f"{execution_time:.2f}s")

        self.console.print(table)

        # Show errors if any
        if errors:
            self.console.print("\n[bold red]Errors:[/]")
            for error in errors:
                self.console.print(f"  [red]- {error}[/]")

    def display_step_detail(self, step: PlanStep) -> None:
        """Display detailed information for a single step.

        Args:
            step: Plan step to display
        """
        icon = self.STATUS_ICONS.get(step.status, "○")
        color = self.STATUS_COLORS.get(step.status, "dim")

        # Create step panel
        content = f"{icon} [{color}]{step.status.value}[/]\n\n{step.description}"

        if step.dependencies:
            deps = ", ".join(step.dependencies)
            content += f"\n\n[dim]Depends on: {deps}[/]"

        if step.details:
            for key, value in step.details.items():
                content += f"\n[dim]{key}: {value}[/]"

        panel = Panel(
            content,
            title=f"[bold]Step {step.id}[/]",
            border_style=color,
        )
        self.console.print(panel)

    def display_complexity_info(self, complexity: ComplexityResult) -> None:
        """Display complexity analysis information.

        Args:
            complexity: Complexity analysis result
        """
        color = self.LEVEL_COLORS.get(complexity.level, "white")

        # Create complexity panel
        content = f"Level: [{color}]{complexity.level.value.upper}[/]\n"
        content += f"Score: {complexity.score}\n"
        content += f"Strategy: {complexity.strategy}\n"

        if complexity.factors:
            content += "\n[dim]Factors:[/]\n"
            for factor in complexity.factors[:5]:  # Limit to top 5 factors
                content += f"  [dim]- {factor}[/]\n"

        panel = Panel(
            content,
            title="[bold]Complexity Analysis[/]",
            border_style=color,
        )
        self.console.print(panel)

    def _display_tree_plan(self, plan: ExecutionPlan, complexity: ComplexityResult) -> None:
        """Display plan in tree format."""
        # Header
        level_color = self.LEVEL_COLORS.get(complexity.level, "white")
        self.console.print(
            Panel(
                f"Strategy: {plan.strategy}\n"
                f"Complexity: [{level_color}]{complexity.level.value}[/] ({complexity.score})\n"
                f"Steps: {plan.total_steps}",
                title="[bold]Execution Plan[/]",
                border_style="blue",
            )
        )

        if not plan.steps:
            self.console.print("[dim]No steps to execute[/]")
            return

        # Build tree
        tree = Tree("[bold]Plan[/]")

        # Group steps by dependencies
        root_steps = [s for s in plan.steps if not s.dependencies]
        dep_steps = [s for s in plan.steps if s.dependencies]

        # Add root steps
        for step in root_steps:
            icon = self.STATUS_ICONS.get(step.status, "○")
            branch = tree.add(f"{icon} {step.id}: {step.description}")

            # Add dependent steps as children
            for dep_step in dep_steps:
                if step.id in dep_step.dependencies:
                    dep_icon = self.STATUS_ICONS.get(dep_step.status, "○")
                    branch.add(f"{dep_icon} {dep_step.id}: {dep_step.description}")

        # Add orphan steps (those whose dependencies aren't in the plan)
        orphan_steps = [
            s
            for s in dep_steps
            if not any(d in [step.id for step in plan.steps] for d in s.dependencies)
        ]
        if orphan_steps:
            orphan_branch = tree.add("[dim]Independent Steps[/]")
            for step in orphan_steps:
                icon = self.STATUS_ICONS.get(step.status, "○")
                orphan_branch.add(f"{icon} {step.id}: {step.description}")

        self.console.print(tree)

    def _display_list_plan(self, plan: ExecutionPlan, complexity: ComplexityResult) -> None:
        """Display plan in list format."""
        # Header
        level_color = self.LEVEL_COLORS.get(complexity.level, "white")
        self.console.print(
            f"\n[bold]Execution Plan[/] "
            f"(Strategy: {plan.strategy}, Complexity: [{level_color}]{complexity.level.value}[/])\n"
        )

        if not plan.steps:
            self.console.print("[dim]No steps to execute[/]")
            return

        # List steps
        for i, step in enumerate(plan.steps, 1):
            icon = self.STATUS_ICONS.get(step.status, "○")
            color = self.STATUS_COLORS.get(step.status, "dim")

            # Show dependencies inline
            deps_str = ""
            if step.dependencies:
                deps_str = f" [dim](depends on: {', '.join(step.dependencies)})[/]"

            self.console.print(f"  {icon} [{color}]{i}. {step.description}[/]{deps_str}")

    def _display_compact_plan(self, plan: ExecutionPlan, complexity: ComplexityResult) -> None:
        """Display plan in compact format for simple tasks."""
        if not plan.steps:
            self.console.print("[dim]Executing directly (no plan needed)[/]")
            return

        # Compact single-line display
        step_descs = [s.description for s in plan.steps[:3]]  # Show max 3 steps
        if len(plan.steps) > 3:
            step_descs.append(f"... (+{len(plan.steps) - 3} more)")

        steps_str = " -> ".join(step_descs)
        self.console.print(f"\n[cyan][Plan][/] {steps_str}\n")

    def create_progress_tracker(self, plan: ExecutionPlan) -> Progress:
        """Create a progress tracker for the plan.

        Args:
            plan: Execution plan to track

        Returns:
            Rich Progress instance
        """
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}[/]"),
            BarColumn(complete_style="green", finished_style="green"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console,
        )

        # Add overall progress task
        progress.add_task(
            "Overall",
            total=plan.total_steps,
        )

        return progress


def create_plan_from_analysis(
    task: str, complexity: ComplexityResult, steps: Optional[List[str]] = None
) -> ExecutionPlan:
    """Create an execution plan from complexity analysis.

    Args:
        task: Task description
        complexity: Complexity analysis result
        steps: Optional list of step descriptions

    Returns:
        ExecutionPlan instance
    """
    # Create default steps based on complexity
    if steps is None:
        if complexity.level == ComplexityLevel.SIMPLE:
            steps = ["Execute task directly"]
        elif complexity.level == ComplexityLevel.MEDIUM:
            steps = [
                "Analyze task requirements",
                "Execute planned actions",
                "Verify results",
            ]
        else:
            steps = [
                "Analyze task requirements",
                "Create execution plan",
                "Execute first iteration",
                "Reflect on results",
                "Refine approach",
                "Execute refined plan",
                "Verify final results",
            ]

    # Create PlanStep objects
    plan_steps = []
    for i, desc in enumerate(steps):
        step_id = f"step_{i + 1}"
        # Add dependencies for complex plans
        deps = []
        if complexity.level == ComplexityLevel.COMPLEX and i > 0:
            deps = [f"step_{i}"]

        plan_steps.append(
            PlanStep(
                id=step_id,
                description=desc,
                status=StepStatus.PENDING,
                dependencies=deps,
            )
        )

    return ExecutionPlan(
        steps=plan_steps,
        total_steps=len(plan_steps),
        strategy=complexity.strategy,
        estimated_time=complexity.score * 0.1,  # Rough estimate
        complexity_score=complexity.score,
    )
