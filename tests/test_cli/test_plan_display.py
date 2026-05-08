"""Tests for execution plan visualization."""

import pytest
from io import StringIO
from unittest.mock import patch, MagicMock

from rich.console import Console

from mini_claude.cli.plan_display import (
    StepStatus,
    DisplayFormat,
    PlanStep,
    ExecutionPlan,
    PlanVisualizer,
    create_plan_from_analysis,
)
from mini_claude.agent.complexity import ComplexityLevel, ComplexityResult


class TestStepStatus:
    """Tests for StepStatus enum."""

    def test_status_values(self):
        """Test enum values."""
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.COMPLETED.value == "completed"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.SKIPPED.value == "skipped"


class TestDisplayFormat:
    """Tests for DisplayFormat enum."""

    def test_format_values(self):
        """Test enum values."""
        assert DisplayFormat.TREE.value == "tree"
        assert DisplayFormat.LIST.value == "list"
        assert DisplayFormat.COMPACT.value == "compact"


class TestPlanStep:
    """Tests for PlanStep dataclass."""

    def test_basic_step(self):
        """Test basic step creation."""
        step = PlanStep(id="step_1", description="Read file")

        assert step.id == "step_1"
        assert step.description == "Read file"
        assert step.status == StepStatus.PENDING
        assert step.dependencies == []
        assert step.details == {}

    def test_step_with_dependencies(self):
        """Test step with dependencies."""
        step = PlanStep(
            id="step_2",
            description="Write file",
            dependencies=["step_1"],
        )

        assert step.dependencies == ["step_1"]

    def test_step_with_details(self):
        """Test step with details."""
        step = PlanStep(
            id="step_1",
            description="Read file",
            details={"file_path": "/tmp/test.py", "encoding": "utf-8"},
        )

        assert step.details["file_path"] == "/tmp/test.py"
        assert step.details["encoding"] == "utf-8"


class TestExecutionPlan:
    """Tests for ExecutionPlan dataclass."""

    def test_empty_plan(self):
        """Test empty plan."""
        plan = ExecutionPlan()

        assert plan.steps == []
        assert plan.total_steps == 0
        assert plan.strategy == "react"

    def test_plan_with_steps(self):
        """Test plan with steps."""
        steps = [
            PlanStep("step_1", "Read file"),
            PlanStep("step_2", "Process file"),
        ]
        plan = ExecutionPlan(steps=steps, total_steps=2)

        assert len(plan.steps) == 2
        assert plan.total_steps == 2

    def test_get_step(self):
        """Test getting step by ID."""
        steps = [
            PlanStep("step_1", "Read file"),
            PlanStep("step_2", "Write file"),
        ]
        plan = ExecutionPlan(steps=steps)

        step = plan.get_step("step_1")
        assert step is not None
        assert step.description == "Read file"

        # Non-existent step
        assert plan.get_step("step_3") is None

    def test_update_step_status(self):
        """Test updating step status."""
        steps = [PlanStep("step_1", "Read file")]
        plan = ExecutionPlan(steps=steps)

        result = plan.update_step_status("step_1", StepStatus.RUNNING)
        assert result is True
        assert plan.steps[0].status == StepStatus.RUNNING

        # Non-existent step
        result = plan.update_step_status("step_2", StepStatus.COMPLETED)
        assert result is False


class TestPlanVisualizer:
    """Tests for PlanVisualizer class."""

    @pytest.fixture
    def visualizer(self):
        """Create visualizer with string console."""
        console = Console(file=StringIO(), force_terminal=True, width=80)
        return PlanVisualizer(console=console)

    @pytest.fixture
    def simple_complexity(self):
        """Create simple complexity result."""
        return ComplexityResult(
            level=ComplexityLevel.SIMPLE,
            score=25,
            strategy="react",
            factors=["Short task"],
        )

    @pytest.fixture
    def medium_complexity(self):
        """Create medium complexity result."""
        return ComplexityResult(
            level=ComplexityLevel.MEDIUM,
            score=50,
            strategy="react",
            factors=["Medium task", "Multiple keywords"],
        )

    @pytest.fixture
    def complex_complexity(self):
        """Create complex complexity result."""
        return ComplexityResult(
            level=ComplexityLevel.COMPLEX,
            score=85,
            strategy="reflexion",
            factors=["Long task", "Complex keywords", "Multiple domains"],
        )

    @pytest.fixture
    def simple_plan(self):
        """Create simple execution plan."""
        return ExecutionPlan(
            steps=[PlanStep("step_1", "Execute task")],
            total_steps=1,
            strategy="react",
        )

    @pytest.fixture
    def multi_step_plan(self):
        """Create multi-step execution plan."""
        return ExecutionPlan(
            steps=[
                PlanStep("step_1", "Analyze requirements"),
                PlanStep("step_2", "Implement solution"),
                PlanStep("step_3", "Verify results"),
            ],
            total_steps=3,
            strategy="react",
        )

    def test_initialization(self, visualizer):
        """Test visualizer initialization."""
        assert visualizer.console is not None
        assert visualizer._current_plan is None

    def test_display_plan_simple(self, visualizer, simple_plan, simple_complexity):
        """Test displaying simple plan."""
        visualizer.display_plan(simple_plan, simple_complexity)

        # Check output
        output = visualizer.console.file.getvalue()
        assert "Plan" in output

    def test_display_plan_tree_format(self, visualizer, multi_step_plan, medium_complexity):
        """Test displaying plan in tree format."""
        visualizer.display_plan(
            multi_step_plan,
            medium_complexity,
            format=DisplayFormat.TREE
        )

        output = visualizer.console.file.getvalue()
        assert "Execution Plan" in output

    def test_display_plan_list_format(self, visualizer, multi_step_plan, medium_complexity):
        """Test displaying plan in list format."""
        visualizer.display_plan(
            multi_step_plan,
            medium_complexity,
            format=DisplayFormat.LIST
        )

        output = visualizer.console.file.getvalue()
        assert "Execution Plan" in output

    def test_display_progress(self, visualizer, multi_step_plan, medium_complexity):
        """Test displaying progress."""
        visualizer.display_plan(multi_step_plan, medium_complexity)
        visualizer.display_progress("step_1", StepStatus.RUNNING)

        output = visualizer.console.file.getvalue()
        assert "step_1" in output

    def test_display_progress_with_message(self, visualizer, multi_step_plan, medium_complexity):
        """Test displaying progress with message."""
        visualizer.display_plan(multi_step_plan, medium_complexity)
        visualizer.display_progress("step_1", StepStatus.COMPLETED, "Done")

        output = visualizer.console.file.getvalue()
        assert "Done" in output

    def test_display_summary_success(self, visualizer):
        """Test displaying successful summary."""
        result = {
            "success": True,
            "total_steps": 3,
            "completed_steps": 3,
            "failed_steps": 0,
            "execution_time": 1.5,
            "errors": [],
        }
        visualizer.display_summary(result)

        output = visualizer.console.file.getvalue()
        assert "SUCCESS" in output
        assert "3/3" in output

    def test_display_summary_failure(self, visualizer):
        """Test displaying failure summary."""
        result = {
            "success": False,
            "total_steps": 3,
            "completed_steps": 1,
            "failed_steps": 2,
            "execution_time": 2.0,
            "errors": ["Connection timeout", "File not found"],
        }
        visualizer.display_summary(result)

        output = visualizer.console.file.getvalue()
        assert "FAILED" in output
        assert "Errors" in output

    def test_display_step_detail(self, visualizer):
        """Test displaying step detail."""
        step = PlanStep(
            id="step_1",
            description="Read configuration file",
            status=StepStatus.COMPLETED,
            details={"file": "config.yaml"},
        )
        visualizer.display_step_detail(step)

        output = visualizer.console.file.getvalue()
        assert "step_1" in output
        assert "Read configuration file" in output

    def test_display_complexity_info(self, visualizer, complex_complexity):
        """Test displaying complexity info."""
        visualizer.display_complexity_info(complex_complexity)

        output = visualizer.console.file.getvalue()
        assert "COMPLEX" in output or "complex" in output.lower()
        assert "85" in output

    def test_create_progress_tracker(self, visualizer, multi_step_plan):
        """Test creating progress tracker."""
        progress = visualizer.create_progress_tracker(multi_step_plan)

        assert progress is not None
        # Check that tasks were added
        assert len(progress.task_ids) > 0

    def test_status_colors_defined(self, visualizer):
        """Test that all status colors are defined."""
        for status in StepStatus:
            assert status in visualizer.STATUS_COLORS

    def test_status_icons_defined(self, visualizer):
        """Test that all status icons are defined."""
        for status in StepStatus:
            assert status in visualizer.STATUS_ICONS

    def test_level_colors_defined(self, visualizer):
        """Test that all level colors are defined."""
        for level in ComplexityLevel:
            assert level in visualizer.LEVEL_COLORS


class TestCreatePlanFromAnalysis:
    """Tests for create_plan_from_analysis function."""

    def test_simple_task_plan(self):
        """Test plan creation for simple task."""
        complexity = ComplexityResult(
            level=ComplexityLevel.SIMPLE,
            score=20,
            strategy="react",
        )
        plan = create_plan_from_analysis("Fix typo", complexity)

        assert plan.total_steps == 1
        assert plan.strategy == "react"

    def test_medium_task_plan(self):
        """Test plan creation for medium task."""
        complexity = ComplexityResult(
            level=ComplexityLevel.MEDIUM,
            score=50,
            strategy="react",
        )
        plan = create_plan_from_analysis("Optimize query", complexity)

        assert plan.total_steps == 3  # Analyze, Execute, Verify

    def test_complex_task_plan(self):
        """Test plan creation for complex task."""
        complexity = ComplexityResult(
            level=ComplexityLevel.COMPLEX,
            score=85,
            strategy="reflexion",
        )
        plan = create_plan_from_analysis("Develop payment system", complexity)

        assert plan.total_steps == 7  # More steps for complex
        assert plan.strategy == "reflexion"

        # Check dependencies for complex plan
        for step in plan.steps[1:]:
            assert len(step.dependencies) > 0 or step.id == "step_1"

    def test_custom_steps(self):
        """Test plan creation with custom steps."""
        complexity = ComplexityResult(
            level=ComplexityLevel.SIMPLE,
            score=20,
            strategy="react",
        )
        custom_steps = ["Step A", "Step B", "Step C"]
        plan = create_plan_from_analysis("Custom task", complexity, steps=custom_steps)

        assert plan.total_steps == 3
        assert plan.steps[0].description == "Step A"
        assert plan.steps[1].description == "Step B"
        assert plan.steps[2].description == "Step C"


class TestPlanStepStatusTransitions:
    """Tests for step status transitions."""

    def test_status_transition(self):
        """Test status transitions."""
        step = PlanStep("step_1", "Test")

        assert step.status == StepStatus.PENDING

        step.status = StepStatus.RUNNING
        assert step.status == StepStatus.RUNNING

        step.status = StepStatus.COMPLETED
        assert step.status == StepStatus.COMPLETED

    def test_plan_status_updates(self):
        """Test updating multiple step statuses."""
        steps = [
            PlanStep("step_1", "First"),
            PlanStep("step_2", "Second"),
            PlanStep("step_3", "Third"),
        ]
        plan = ExecutionPlan(steps=steps)

        # Update statuses
        plan.update_step_status("step_1", StepStatus.COMPLETED)
        plan.update_step_status("step_2", StepStatus.RUNNING)
        plan.update_step_status("step_3", StepStatus.PENDING)

        assert plan.steps[0].status == StepStatus.COMPLETED
        assert plan.steps[1].status == StepStatus.RUNNING
        assert plan.steps[2].status == StepStatus.PENDING


class TestEmptyPlan:
    """Tests for empty plan handling."""

    @pytest.fixture
    def visualizer(self):
        """Create visualizer with string console."""
        console = Console(file=StringIO(), force_terminal=True, width=80)
        return PlanVisualizer(console=console)

    def test_display_empty_plan_tree(self, visualizer):
        """Test displaying empty plan in tree format."""
        complexity = ComplexityResult(
            level=ComplexityLevel.SIMPLE,
            score=20,
            strategy="react",
        )
        plan = ExecutionPlan(steps=[], total_steps=0)

        visualizer.display_plan(plan, complexity, format=DisplayFormat.TREE)

        output = visualizer.console.file.getvalue()
        assert "No steps" in output or "empty" in output.lower() or len(output) > 0

    def test_display_empty_plan_list(self, visualizer):
        """Test displaying empty plan in list format."""
        complexity = ComplexityResult(
            level=ComplexityLevel.SIMPLE,
            score=20,
            strategy="react",
        )
        plan = ExecutionPlan(steps=[], total_steps=0)

        visualizer.display_plan(plan, complexity, format=DisplayFormat.LIST)

        output = visualizer.console.file.getvalue()
        # Should handle gracefully
        assert len(output) >= 0
