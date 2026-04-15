"""Sub-agent manager for parallel execution."""

import asyncio
from typing import Dict, Any, Callable, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from mini_claude.config.settings import settings


class AgentStatus(Enum):
    """Status of a sub-agent."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SubAgentResult:
    """Result from a sub-agent execution."""
    agent_id: str
    status: AgentStatus
    output: Any = None
    error: Optional[str] = None
    progress: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    messages: List[dict] = field(default_factory=list)


class SubAgentManager:
    """Manages parallel sub-agent execution."""

    def __init__(self, max_concurrent: Optional[int] = None):
        self.max_concurrent = max_concurrent or settings.max_sub_agents
        self.agents: Dict[str, asyncio.Task] = {}
        self.results: Dict[str, SubAgentResult] = {}
        self.progress_queue: asyncio.Queue = asyncio.Queue()
        self.semaphore = asyncio.Semaphore(self.max_concurrent)

    async def spawn(
        self,
        agent_id: str,
        task: Callable,
        *args,
        **kwargs
    ) -> str:
        """Spawn a single sub-agent."""
        if agent_id in self.agents:
            raise ValueError(f"Agent {agent_id} already exists")

        self.results[agent_id] = SubAgentResult(
            agent_id=agent_id,
            status=AgentStatus.PENDING,
            started_at=datetime.now(),
        )

        async def wrapped_task():
            async with self.semaphore:
                self.results[agent_id].status = AgentStatus.RUNNING
                try:
                    result = await task(
                        *args,
                        progress_callback=self._make_callback(agent_id),
                        **kwargs
                    )
                    self.results[agent_id].status = AgentStatus.COMPLETED
                    self.results[agent_id].output = result
                    self.results[agent_id].progress = 1.0
                except Exception as e:
                    self.results[agent_id].status = AgentStatus.FAILED
                    self.results[agent_id].error = str(e)
                finally:
                    self.results[agent_id].completed_at = datetime.now()
                return self.results[agent_id]

        self.agents[agent_id] = asyncio.create_task(wrapped_task())
        return agent_id

    async def spawn_parallel(
        self,
        tasks: List[tuple]
    ) -> List[str]:
        """Spawn multiple sub-agents in parallel.

        Args:
            tasks: List of (agent_id, task_callable, args, kwargs) tuples

        Returns:
            List of agent IDs
        """
        agent_ids = []
        for agent_id, task_callable, args, kwargs in tasks:
            await self.spawn(agent_id, task_callable, *args, **kwargs)
            agent_ids.append(agent_id)
        return agent_ids

    async def wait_for_all(self) -> Dict[str, SubAgentResult]:
        """Wait for all agents to complete."""
        if self.agents:
            await asyncio.gather(*self.agents.values(), return_exceptions=True)
        return self.results

    async def wait_for_one(self, agent_id: str) -> SubAgentResult:
        """Wait for a specific agent to complete."""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found")
        return await self.agents[agent_id]

    def get_status(self) -> Dict[str, dict]:
        """Get status of all agents."""
        return {
            agent_id: {
                "status": result.status.value,
                "progress": result.progress,
                "output": result.output,
                "error": result.error,
            }
            for agent_id, result in self.results.items()
        }

    def get_completed_results(self) -> Dict[str, Any]:
        """Get results from completed agents."""
        return {
            agent_id: result.output
            for agent_id, result in self.results.items()
            if result.status == AgentStatus.COMPLETED
        }

    def _make_callback(self, agent_id: str) -> Callable:
        """Create a progress callback for an agent."""
        async def callback(progress: float, message: str = ""):
            self.results[agent_id].progress = progress
            await self.progress_queue.put((agent_id, progress, message))
        return callback

    async def get_progress_update(self, timeout: float = 0.1) -> Optional[tuple]:
        """Get the next progress update (non-blocking)."""
        try:
            return await asyncio.wait_for(
                self.progress_queue.get(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return None

    def clear(self):
        """Clear all agents and results."""
        self.agents.clear()
        self.results.clear()


# Global sub-agent manager
subagent_manager = SubAgentManager()
