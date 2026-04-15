"""Enhanced parallel execution with auto-aggregation and smart task distribution."""

import asyncio
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from mini_claude.config.settings import settings


class TaskPriority(Enum):
    """Priority levels for tasks."""
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class TaskStatus(Enum):
    """Status of a distributed task."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DistributedTask:
    """A task for parallel execution."""
    id: str
    description: str
    target_files: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # Task IDs this depends on
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class AgentInfo:
    """Information about a sub-agent."""
    id: str
    status: str = "idle"
    current_task: Optional[str] = None
    completed_tasks: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)


class ParallelCoordinator:
    """Coordinates parallel agent execution with smart task distribution."""

    def __init__(self, max_agents: Optional[int] = None):
        self.max_agents = max_agents or settings.max_sub_agents
        self.tasks: Dict[str, DistributedTask] = {}
        self.agents: Dict[str, AgentInfo] = {}
        self.results: Dict[str, Any] = {}
        self.progress_callbacks: List[Callable] = []
        self._lock = asyncio.Lock()

    def add_progress_callback(self, callback: Callable) -> None:
        """Add a callback for progress updates."""
        self.progress_callbacks.append(callback)

    async def _notify_progress(self, event: str, data: Dict) -> None:
        """Notify all progress callbacks."""
        for callback in self.progress_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event, data)
                else:
                    callback(event, data)
            except Exception:
                pass

    def add_task(
        self,
        task_id: str,
        description: str,
        target_files: List[str] = None,
        dependencies: List[str] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
    ) -> DistributedTask:
        """Add a task to the queue."""
        task = DistributedTask(
            id=task_id,
            description=description,
            target_files=target_files or [],
            dependencies=dependencies or [],
            priority=priority,
        )
        self.tasks[task_id] = task
        return task

    def analyze_dependencies(self) -> Dict[str, List[str]]:
        """Analyze task dependencies and return execution order.

        Returns:
            Dict mapping execution level to list of task IDs that can run in parallel
        """
        # Build dependency graph
        in_degree: Dict[str, int] = {tid: 0 for tid in self.tasks}
        dependents: Dict[str, List[str]] = {tid: [] for tid in self.tasks}

        for tid, task in self.tasks.items():
            for dep in task.dependencies:
                if dep in self.tasks:
                    in_degree[tid] += 1
                    dependents[dep].append(tid)

        # Topological sort with levels
        levels: Dict[str, List[str]] = {}
        current_level = 0
        remaining = set(self.tasks.keys())

        while remaining:
            # Find tasks with no pending dependencies
            ready = [tid for tid in remaining if in_degree[tid] == 0]

            if not ready:
                # Circular dependency detected
                raise ValueError(f"Circular dependency detected among tasks: {remaining}")

            levels[f"level_{current_level}"] = ready

            # Update in-degrees
            for tid in ready:
                for dependent in dependents[tid]:
                    in_degree[dependent] -= 1

            remaining -= set(ready)
            current_level += 1

        return levels

    def get_ready_tasks(self) -> List[DistributedTask]:
        """Get tasks that are ready to execute (all dependencies satisfied)."""
        ready = []
        for tid, task in self.tasks.items():
            if task.status != TaskStatus.PENDING:
                continue

            # Check if all dependencies are completed
            deps_satisfied = all(
                self.tasks.get(dep, DistributedTask(id="", description="")).status == TaskStatus.COMPLETED
                for dep in task.dependencies
            )

            if deps_satisfied:
                ready.append(task)

        # Sort by priority (HIGH first)
        ready.sort(key=lambda t: t.priority.value)
        return ready

    def assign_task(self, task_id: str, agent_id: str) -> bool:
        """Assign a task to an agent."""
        if task_id not in self.tasks:
            return False

        task = self.tasks[task_id]
        if task.status != TaskStatus.PENDING:
            return False

        task.status = TaskStatus.ASSIGNED
        task.assigned_agent = agent_id

        if agent_id not in self.agents:
            self.agents[agent_id] = AgentInfo(id=agent_id)

        self.agents[agent_id].current_task = task_id
        self.agents[agent_id].status = "busy"

        return True

    def mark_task_running(self, task_id: str) -> None:
        """Mark a task as running."""
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.RUNNING
            self.tasks[task_id].started_at = datetime.now()

    def mark_task_completed(self, task_id: str, result: str) -> None:
        """Mark a task as completed with result."""
        if task_id not in self.tasks:
            return

        task = self.tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.completed_at = datetime.now()

        self.results[task_id] = result

        # Update agent status
        if task.assigned_agent and task.assigned_agent in self.agents:
            agent = self.agents[task.assigned_agent]
            agent.current_task = None
            agent.status = "idle"
            agent.completed_tasks.append(task_id)

    def mark_task_failed(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        if task_id not in self.tasks:
            return

        task = self.tasks[task_id]
        task.status = TaskStatus.FAILED
        task.error = error
        task.completed_at = datetime.now()

        # Update agent status
        if task.assigned_agent and task.assigned_agent in self.agents:
            self.agents[task.assigned_agent].current_task = None
            self.agents[task.assigned_agent].status = "idle"

    def get_status_report(self) -> Dict[str, Any]:
        """Get a comprehensive status report."""
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        running = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)
        pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
        failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)

        return {
            "total_tasks": total,
            "completed": completed,
            "running": running,
            "pending": pending,
            "failed": failed,
            "progress": f"{completed}/{total}" if total > 0 else "0/0",
            "progress_percent": (completed / total * 100) if total > 0 else 0,
            "agents": {
                aid: {
                    "status": agent.status,
                    "current_task": agent.current_task,
                    "completed_count": len(agent.completed_tasks),
                }
                for aid, agent in self.agents.items()
            },
            "tasks": {
                tid: {
                    "status": task.status.value,
                    "assigned_to": task.assigned_agent,
                    "has_result": task.result is not None,
                }
                for tid, task in self.tasks.items()
            },
        }

    def aggregate_results(self) -> str:
        """Aggregate all completed task results into a summary."""
        completed_tasks = [
            t for t in self.tasks.values()
            if t.status == TaskStatus.COMPLETED
        ]

        if not completed_tasks:
            return "No completed tasks to aggregate."

        lines = ["=== Parallel Execution Results ===\n"]

        # Group by status
        lines.append(f"Total: {len(self.tasks)} tasks")
        lines.append(f"Completed: {len(completed_tasks)}")
        lines.append(f"Failed: {sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)}")
        lines.append("")

        # Individual results
        lines.append("--- Task Results ---\n")
        for task in sorted(completed_tasks, key=lambda t: t.id):
            lines.append(f"## {task.id}")
            lines.append(f"Description: {task.description}")
            if task.assigned_agent:
                lines.append(f"Executed by: {task.assigned_agent}")
            if task.result:
                # Truncate long results
                result = task.result[:500] + "..." if len(task.result) > 500 else task.result
                lines.append(f"Result:\n{result}")
            lines.append("")

        # Failed tasks
        failed_tasks = [t for t in self.tasks.values() if t.status == TaskStatus.FAILED]
        if failed_tasks:
            lines.append("--- Failed Tasks ---\n")
            for task in failed_tasks:
                lines.append(f"- {task.id}: {task.error}")

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all tasks and results."""
        self.tasks.clear()
        self.agents.clear()
        self.results.clear()


# Global coordinator
parallel_coordinator = ParallelCoordinator()
