"""Tests for ExecutionPlan integration with AgentState."""

from mini_claude.agent.state import AgentState, create_initial_state
from mini_claude.cli.plan_display import (
    StepStatus,
    PlanStep,
    ExecutionPlan,
    create_plan_from_analysis,
)
from mini_claude.agent.complexity import ComplexityLevel, ComplexityResult


class TestExecutionPlanStateIntegration:
    """Tests for ExecutionPlan integration with AgentState."""

    def test_state_has_execution_plan_field(self):
        """Test that AgentState has execution_plan field."""
        state = create_initial_state("test task")
        # TypedDict instances are plain dicts; check annotations on the class
        assert "execution_plan" in AgentState.__annotations__
        assert "current_step_index" in AgentState.__annotations__
        assert state["execution_plan"] is None
        assert state["current_step_index"] == 0

    def test_state_can_store_serialized_plan(self):
        """Test that state can store serialized execution plan."""
        # Create a plan
        complexity = ComplexityResult(
            level=ComplexityLevel.MEDIUM,
            score=50,
            strategy="react",
            factors=["test"],
        )
        plan = create_plan_from_analysis("test task", complexity)

        # Serialize plan
        serialized_plan = {
            "steps": [
                {
                    "id": step.id,
                    "description": step.description,
                    "status": step.status.value
                    if hasattr(step.status, "value")
                    else str(step.status),
                    "dependencies": step.dependencies,
                    "details": step.details,
                }
                for step in plan.steps
            ],
            "total_steps": plan.total_steps,
            "strategy": plan.strategy,
            "estimated_time": plan.estimated_time,
            "complexity_score": plan.complexity_score,
        }

        # Store in state
        state = create_initial_state("test task")
        state["execution_plan"] = serialized_plan
        state["current_step_index"] = 1

        assert state["execution_plan"] is not None
        assert state["execution_plan"]["total_steps"] == 3
        assert state["current_step_index"] == 1

    def test_plan_step_status_update(self):
        """Test updating step status in serialized plan."""
        # Create serialized plan
        serialized_plan = {
            "steps": [
                {
                    "id": "step_1",
                    "description": "First step",
                    "status": "pending",
                    "dependencies": [],
                    "details": {},
                },
                {
                    "id": "step_2",
                    "description": "Second step",
                    "status": "pending",
                    "dependencies": ["step_1"],
                    "details": {},
                },
            ],
            "total_steps": 2,
            "strategy": "react",
            "estimated_time": 1.0,
            "complexity_score": 50,
        }

        # Update first step to running
        updated_plan = dict(serialized_plan)
        updated_steps = list(updated_plan["steps"])
        updated_steps[0] = dict(updated_steps[0])
        updated_steps[0]["status"] = "running"
        updated_plan["steps"] = updated_steps

        assert updated_plan["steps"][0]["status"] == "running"
        assert updated_plan["steps"][1]["status"] == "pending"

        # Update first step to completed
        updated_steps[0] = dict(updated_steps[0])
        updated_steps[0]["status"] = "completed"
        updated_plan["steps"] = updated_steps

        assert updated_plan["steps"][0]["status"] == "completed"


class TestPlanNodeIntegration:
    """Tests for plan_node integration with ExecutionPlan."""

    def test_serialize_plan_function(self):
        """Test _serialize_plan function in plan.py."""
        from mini_claude.agent.nodes.plan import _serialize_plan

        # Create a plan
        step1 = PlanStep(id="step_1", description="First step", status=StepStatus.PENDING)
        step2 = PlanStep(
            id="step_2",
            description="Second step",
            status=StepStatus.PENDING,
            dependencies=["step_1"],
        )
        plan = ExecutionPlan(
            steps=[step1, step2],
            total_steps=2,
            strategy="react",
            estimated_time=1.0,
            complexity_score=50,
        )

        # Serialize
        serialized = _serialize_plan(plan)

        assert serialized["total_steps"] == 2
        assert serialized["strategy"] == "react"
        assert len(serialized["steps"]) == 2
        assert serialized["steps"][0]["id"] == "step_1"
        assert serialized["steps"][0]["status"] == "pending"
        assert serialized["steps"][1]["dependencies"] == ["step_1"]


class TestActNodePlanUpdate:
    """Tests for act_node plan status update functions."""

    def test_update_plan_step_status_function(self):
        """Test _update_plan_step_status function in act.py."""
        from mini_claude.agent.nodes.act import _update_plan_step_status

        # Create serialized plan
        plan = {
            "steps": [
                {"id": "step_1", "description": "First", "status": "pending"},
                {"id": "step_2", "description": "Second", "status": "pending"},
            ],
            "total_steps": 2,
        }

        # Update step 0 to running
        updated = _update_plan_step_status(plan, 0, "running")
        assert updated["steps"][0]["status"] == "running"
        assert updated["steps"][1]["status"] == "pending"

        # Update step 0 to completed
        updated = _update_plan_step_status(updated, 0, "completed")
        assert updated["steps"][0]["status"] == "completed"

        # Update step 1 to running
        updated = _update_plan_step_status(updated, 1, "running")
        assert updated["steps"][1]["status"] == "running"

    def test_update_plan_step_status_invalid_index(self):
        """Test updating with invalid step index."""
        from mini_claude.agent.nodes.act import _update_plan_step_status

        plan = {
            "steps": [{"id": "step_1", "status": "pending"}],
            "total_steps": 1,
        }

        # Invalid index should return unchanged
        updated = _update_plan_step_status(plan, 10, "running")
        assert updated == plan

    def test_get_plan_progress_message(self):
        """Test _get_plan_progress_message function."""
        from mini_claude.agent.nodes.act import _get_plan_progress_message

        plan = {
            "steps": [
                {"id": "step_1", "description": "Analyze requirements"},
                {"id": "step_2", "description": "Execute actions"},
                {"id": "step_3", "description": "Verify results"},
            ],
            "total_steps": 3,
        }

        # Get progress message for step 0
        msg = _get_plan_progress_message(plan, 0)
        assert "步骤 1/3" in msg
        assert "Analyze requirements" in msg

        # Get progress message for step 2
        msg = _get_plan_progress_message(plan, 2)
        assert "步骤 3/3" in msg
        assert "Verify results" in msg

    def test_get_plan_progress_message_empty_plan(self):
        """Test progress message with empty plan."""
        from mini_claude.agent.nodes.act import _get_plan_progress_message

        msg = _get_plan_progress_message(None, 0)
        assert msg == ""

        msg = _get_plan_progress_message({}, 0)
        assert msg == ""

        msg = _get_plan_progress_message({"steps": []}, 0)
        assert msg == ""


class TestExecutionPlanFlow:
    """End-to-end tests for execution plan flow."""

    def test_full_plan_flow(self):
        """Test complete flow: create -> store -> update -> verify."""
        # 1. Create initial state
        state = create_initial_state("Create a web application with FastAPI")
        assert state["execution_plan"] is None
        assert state["current_step_index"] == 0

        # 2. Simulate plan creation (as plan_node would do)
        complexity = ComplexityResult(
            level=ComplexityLevel.COMPLEX,
            score=75,
            strategy="reflexion",
            factors=["multiple files", "api"],
        )
        plan = create_plan_from_analysis("Create a web application", complexity)

        # 3. Serialize and store
        from mini_claude.agent.nodes.plan import _serialize_plan

        serialized = _serialize_plan(plan)

        state["execution_plan"] = serialized
        state["current_step_index"] = 0

        # 4. Simulate step execution (as act_node would do)
        from mini_claude.agent.nodes.act import _update_plan_step_status

        # Step 0: running -> completed
        state["execution_plan"] = _update_plan_step_status(state["execution_plan"], 0, "running")
        assert state["execution_plan"]["steps"][0]["status"] == "running"

        state["execution_plan"] = _update_plan_step_status(state["execution_plan"], 0, "completed")
        state["current_step_index"] = 1
        assert state["execution_plan"]["steps"][0]["status"] == "completed"

        # Step 1: running -> completed
        state["execution_plan"] = _update_plan_step_status(state["execution_plan"], 1, "running")
        state["execution_plan"] = _update_plan_step_status(state["execution_plan"], 1, "completed")
        state["current_step_index"] = 2

        # 5. Verify final state
        assert state["current_step_index"] == 2
        assert state["execution_plan"]["steps"][0]["status"] == "completed"
        assert state["execution_plan"]["steps"][1]["status"] == "completed"
