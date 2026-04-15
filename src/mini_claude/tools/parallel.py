"""Enhanced parallel execution tools with auto-aggregation."""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base import BaseTool, register_tool
from ..agent.coordinator import (
    parallel_coordinator, DistributedTask, TaskPriority, TaskStatus
)
from ..agent.subagent import subagent_manager
from ..utils.file_lock import file_lock_manager


class PlanParallelTool(BaseTool):
    """Plan parallel execution with dependency analysis."""

    @property
    def name(self) -> str:
        return "plan_parallel"

    @property
    def description(self) -> str:
        return "Plan parallel task execution with dependency analysis and file conflict detection"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Unique task ID"},
                            "description": {"type": "string", "description": "Task description"},
                            "target_files": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Files this task will modify",
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Task IDs this depends on",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                                "description": "Task priority",
                            },
                        },
                        "required": ["id", "description"],
                    },
                    "description": "List of tasks to plan",
                },
            },
            "required": ["tasks"],
        }

    async def execute(self, tasks: List[Dict]) -> str:
        # Clear previous tasks
        parallel_coordinator.clear()

        # Add tasks
        for task_data in tasks:
            priority = TaskPriority.MEDIUM
            if task_data.get("priority") == "high":
                priority = TaskPriority.HIGH
            elif task_data.get("priority") == "low":
                priority = TaskPriority.LOW

            parallel_coordinator.add_task(
                task_id=task_data["id"],
                description=task_data["description"],
                target_files=task_data.get("target_files", []),
                dependencies=task_data.get("depends_on", []),
                priority=priority,
            )

        # Analyze dependencies
        try:
            levels = parallel_coordinator.analyze_dependencies()
        except ValueError as e:
            return f"Error: {e}"

        # Check for file conflicts
        file_conflicts = self._detect_file_conflicts(tasks)

        # Build response
        lines = ["=== Parallel Execution Plan ===\n"]
        lines.append(f"Total tasks: {len(tasks)}")
        lines.append(f"Execution levels: {len(levels)}\n")

        for level_name, task_ids in levels.items():
            level_num = level_name.split("_")[1]
            lines.append(f"Level {level_num} (parallel):")
            for tid in task_ids:
                task = parallel_coordinator.tasks[tid]
                files_info = f" → {', '.join(task.target_files)}" if task.target_files else ""
                lines.append(f"  - {tid}: {task.description}{files_info}")
            lines.append("")

        if file_conflicts:
            lines.append("⚠️ Potential file conflicts detected:")
            for conflict in file_conflicts:
                lines.append(f"  - {conflict['file']}: tasks {conflict['tasks']}")
            lines.append("")

        lines.append("Use 'execute_parallel' to start execution.")

        return "\n".join(lines)

    def _detect_file_conflicts(self, tasks: List[Dict]) -> List[Dict]:
        """Detect tasks that modify the same files."""
        file_to_tasks: Dict[str, List[str]] = {}
        conflicts = []

        for task in tasks:
            for file in task.get("target_files", []):
                if file not in file_to_tasks:
                    file_to_tasks[file] = []
                file_to_tasks[file].append(task["id"])

        for file, task_ids in file_to_tasks.items():
            if len(task_ids) > 1:
                conflicts.append({"file": file, "tasks": task_ids})

        return conflicts


class ExecuteParallelTool(BaseTool):
    """Execute planned parallel tasks with auto-aggregation."""

    @property
    def name(self) -> str:
        return "execute_parallel"

    @property
    def description(self) -> str:
        return "Execute planned parallel tasks with automatic result aggregation"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "auto_aggregate": {
                    "type": "boolean",
                    "description": "Automatically aggregate results when complete (default: true)",
                },
            },
            "required": [],
        }

    async def execute(self, auto_aggregate: bool = True) -> str:
        if not parallel_coordinator.tasks:
            return "Error: No tasks planned. Use 'plan_parallel' first."

        # Get execution levels
        try:
            levels = parallel_coordinator.analyze_dependencies()
        except ValueError as e:
            return f"Error: {e}"

        total_tasks = len(parallel_coordinator.tasks)
        lines = [f"Starting parallel execution of {total_tasks} tasks...\n"]

        # Execute level by level
        for level_name, task_ids in levels.items():
            level_num = level_name.split("_")[1]
            lines.append(f"[Level {level_num}] Executing {len(task_ids)} task(s) in parallel...")

            # Create tasks for this level
            async def run_task(task_id: str):
                task = parallel_coordinator.tasks[task_id]
                agent_id = f"agent_{task_id}"

                # Assign task
                parallel_coordinator.assign_task(task_id, agent_id)
                parallel_coordinator.mark_task_running(task_id)

                try:
                    # Execute via sub-agent
                    result = await self._execute_task_via_agent(task, agent_id)
                    parallel_coordinator.mark_task_completed(task_id, result)
                    return task_id, True, result
                except Exception as e:
                    parallel_coordinator.mark_task_failed(task_id, str(e))
                    return task_id, False, str(e)

            # Run all tasks in this level concurrently
            results = await asyncio.gather(*[run_task(tid) for tid in task_ids])

            # Report results
            for task_id, success, result in results:
                status = "✓" if success else "✗"
                lines.append(f"  {status} {task_id}")

        lines.append(f"\nExecution complete!")

        # Auto-aggregate if requested
        if auto_aggregate:
            summary = parallel_coordinator.aggregate_results()
            return summary

        return "\n".join(lines)

    async def _execute_task_via_agent(self, task: DistributedTask, agent_id: str) -> str:
        """Execute a single task via sub-agent."""
        from ..agent.graph import build_agent_graph_no_checkpoint
        from ..agent.state import create_initial_state
        from ..tools.file_ops import set_current_agent
        from langchain_core.messages import AIMessage

        # Set agent ID for file locking
        set_current_agent(agent_id)

        # Build prompt
        prompt = f"""Complete this task: {task.description}

Target files: {', '.join(task.target_files) if task.target_files else 'None specified'}

Focus only on this specific task. When complete, provide a clear summary of what was done."""

        # Execute
        graph = build_agent_graph_no_checkpoint()
        state = create_initial_state(prompt, thread_id=agent_id)

        result = await graph.ainvoke(state)

        # Extract result
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and not getattr(msg, 'tool_calls', None):
                return msg.content

        return messages[-1].content if messages else "No result"


class ParallelStatusTool(BaseTool):
    """Get status of parallel execution."""

    @property
    def name(self) -> str:
        return "parallel_status"

    @property
    def description(self) -> str:
        return "Get detailed status of parallel task execution"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self) -> str:
        report = parallel_coordinator.get_status_report()

        lines = ["=== Parallel Execution Status ===\n"]
        lines.append(f"Progress: {report['progress']} ({report['progress_percent']:.1f}%)")
        lines.append(f"Completed: {report['completed']}")
        lines.append(f"Running: {report['running']}")
        lines.append(f"Pending: {report['pending']}")
        lines.append(f"Failed: {report['failed']}")

        if report['agents']:
            lines.append("\n--- Agents ---")
            for aid, info in report['agents'].items():
                lines.append(f"  {aid}: {info['status']}")
                if info['current_task']:
                    lines.append(f"    Working on: {info['current_task']}")
                lines.append(f"    Completed: {info['completed_count']} tasks")

        return "\n".join(lines)


class AggregateResultsTool(BaseTool):
    """Aggregate results from parallel execution."""

    @property
    def name(self) -> str:
        return "aggregate_results"

    @property
    def description(self) -> str:
        return "Aggregate and summarize all parallel task results"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["summary", "detailed", "json"],
                    "description": "Output format (default: summary)",
                },
            },
            "required": [],
        }

    async def execute(self, format: str = "summary") -> str:
        if not parallel_coordinator.results:
            return "No results to aggregate."

        if format == "json":
            import json
            return json.dumps(parallel_coordinator.get_status_report(), indent=2)

        return parallel_coordinator.aggregate_results()


# Register enhanced parallel tools
register_tool(PlanParallelTool())
register_tool(ExecuteParallelTool())
register_tool(ParallelStatusTool())
register_tool(AggregateResultsTool())
