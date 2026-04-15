"""Agent spawning tools."""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base import BaseTool, register_tool
from ..agent.subagent import subagent_manager, AgentStatus
from ..agent.state import create_initial_state
from ..llm.prompts import get_subagent_prompt


class SpawnAgentTool(BaseTool):
    """Spawn a sub-agent for parallel execution."""

    @property
    def name(self) -> str:
        return "spawn_agent"

    @property
    def description(self) -> str:
        return "Spawn a sub-agent to handle a specific task in parallel"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task description for the sub-agent",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context for the task",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Optional ID for the agent (auto-generated if not provided)",
                },
            },
            "required": ["task"],
        }

    async def execute(
        self,
        task: str,
        context: str = "",
        agent_id: str = None
    ) -> str:
        # Generate agent ID if not provided
        if not agent_id:
            timestamp = datetime.now().strftime("%H%M%S")
            agent_id = f"subagent_{timestamp}"

        # Create sub-agent task with full tool loop
        async def subagent_task(progress_callback=None):
            from ..agent.graph import build_agent_graph_no_checkpoint
            from ..agent.state import create_initial_state
            from ..llm.prompts import get_subagent_prompt
            from langchain_core.messages import AIMessage

            if progress_callback:
                await progress_callback(0.1, "Starting sub-agent")

            # Get specialized prompt
            prompt = get_subagent_prompt(task, context)

            if progress_callback:
                await progress_callback(0.3, "Processing task")

            try:
                # Use full graph with tool loop
                graph = build_agent_graph_no_checkpoint()
                state = create_initial_state(prompt, thread_id=agent_id)

                result = await graph.ainvoke(state)

                if progress_callback:
                    await progress_callback(1.0, "Task complete")

                # Extract final response from messages
                messages = result.get("messages", [])
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage) and not getattr(msg, 'tool_calls', None):
                        return msg.content

                return messages[-1].content if messages else "No result"

            except Exception as e:
                if progress_callback:
                    await progress_callback(1.0, f"Error: {e}")
                return f"Error: {e}"

        # Spawn the agent
        try:
            await subagent_manager.spawn(agent_id, subagent_task)
            return f"Spawned sub-agent: {agent_id}\nTask: {task}"
        except Exception as e:
            return f"Error spawning agent: {e}"


class ListAgentsTool(BaseTool):
    """List all active sub-agents."""

    @property
    def name(self) -> str:
        return "list_agents"

    @property
    def description(self) -> str:
        return "List all active sub-agents and their status"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self) -> str:
        status = subagent_manager.get_status()

        if not status:
            return "No active sub-agents"

        lines = ["Active sub-agents:"]
        for agent_id, info in status.items():
            status_str = info["status"]
            progress = info.get("progress", 0) * 100
            lines.append(f"  {agent_id}: {status_str} ({progress:.0f}%)")

            if info.get("error"):
                lines.append(f"    Error: {info['error']}")

        return "\n".join(lines)


class GetResultTool(BaseTool):
    """Get result from a sub-agent."""

    @property
    def name(self) -> str:
        return "get_result"

    @property
    def description(self) -> str:
        return "Get the result from a completed sub-agent"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "ID of the sub-agent to get result from",
                },
                "wait": {
                    "type": "boolean",
                    "description": "Wait for completion if still running (default: false)",
                },
            },
            "required": ["agent_id"],
        }

    async def execute(self, agent_id: str, wait: bool = False) -> str:
        status = subagent_manager.get_status()

        if agent_id not in status:
            return f"Error: Agent {agent_id} not found"

        agent_status = status[agent_id]

        if agent_status["status"] == AgentStatus.RUNNING.value:
            if wait:
                result = await subagent_manager.wait_for_one(agent_id)
                return f"Result from {agent_id}:\n{result.output}"
            else:
                return f"Agent {agent_id} is still running ({agent_status['progress']*100:.0f}%)"

        elif agent_status["status"] == AgentStatus.COMPLETED.value:
            output = agent_status.get("output", "(no output)")
            return f"Result from {agent_id}:\n{output}"

        elif agent_status["status"] == AgentStatus.FAILED.value:
            error = agent_status.get("error", "Unknown error")
            return f"Agent {agent_id} failed: {error}"

        else:
            return f"Agent {agent_id} status: {agent_status['status']}"


class SpawnParallelTool(BaseTool):
    """Spawn multiple agents in parallel."""

    @property
    def name(self) -> str:
        return "spawn_parallel"

    @property
    def description(self) -> str:
        return "Spawn multiple sub-agents to work in parallel"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task descriptions",
                },
            },
            "required": ["tasks"],
        }

    async def execute(self, tasks: List[str]) -> str:
        if not tasks:
            return "Error: No tasks provided"

        # Create task definitions
        task_defs = []
        for i, task in enumerate(tasks):
            agent_id = f"parallel_{i}_{datetime.now().strftime('%H%M%S')}"

            async def subagent_task(t=task, aid=agent_id, progress_callback=None):
                from ..agent.graph import build_agent_graph_no_checkpoint
                from ..agent.state import create_initial_state
                from langchain_core.messages import AIMessage

                if progress_callback:
                    await progress_callback(0.1, "Starting")

                try:
                    graph = build_agent_graph_no_checkpoint()
                    state = create_initial_state(t, thread_id=aid)

                    result = await graph.ainvoke(state)

                    if progress_callback:
                        await progress_callback(1.0, "Done")

                    # Extract final response
                    messages = result.get("messages", [])
                    for msg in reversed(messages):
                        if isinstance(msg, AIMessage) and not getattr(msg, 'tool_calls', None):
                            return msg.content

                    return messages[-1].content if messages else "No result"

                except Exception as e:
                    if progress_callback:
                        await progress_callback(1.0, f"Error: {e}")
                    return f"Error: {e}"

            task_defs.append((agent_id, subagent_task, (), {}))

        # Spawn all in parallel
        try:
            agent_ids = await subagent_manager.spawn_parallel(task_defs)
            return f"Spawned {len(agent_ids)} parallel agents:\n" + "\n".join(f"  - {aid}" for aid in agent_ids)
        except Exception as e:
            return f"Error spawning parallel agents: {e}"


# Register agent tools
register_tool(SpawnAgentTool())
register_tool(ListAgentsTool())
register_tool(GetResultTool())
register_tool(SpawnParallelTool())
