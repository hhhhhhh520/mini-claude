"""Agent spawning tools."""

import asyncio
import time
from typing import Dict, Any, List
from datetime import datetime

from .base import BaseTool, register_tool
from ..agent.subagent import subagent_manager, AgentStatus
from ..agent.state import create_initial_state
from ..llm.prompts import get_subagent_prompt
from ..utils import generate_agent_id
from ..utils.logger import get_logger

logger = get_logger("mini_claude.tools.agent_spawn")


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

    @property
    def examples(self) -> list:
        return [
            {
                "description": "Spawn agent to analyze a file",
                "input": {
                    "task": "Analyze the code structure in src/main.py and identify potential improvements",
                    "context": "Focus on code quality and performance",
                },
                "expected_output": "Spawned sub-agent: subagent_001\nTask: Analyze the code structure...",
            },
            {
                "description": "Spawn agent for documentation generation",
                "input": {
                    "task": "Generate API documentation for the endpoints in routes.py",
                    "agent_id": "doc_gen_01",
                },
                "expected_output": "Spawned sub-agent: doc_gen_01\nTask: Generate API documentation...",
            },
            {
                "description": "Spawn agent for code review",
                "input": {
                    "task": "Review the authentication module for security issues",
                    "context": "Check for OWASP Top 10 vulnerabilities",
                },
                "expected_output": "Spawned sub-agent: subagent_002\nTask: Review the authentication module...",
            },
        ]

    def _extract_subagent_result(self, messages: list) -> str:
        """Extract complete result from sub-agent messages.

        Priority:
        1. Last non-empty AIMessage content (LLM summary of results)
        2. All tool results concatenated (if no AI summary)
        3. Last message content as fallback

        Args:
            messages: List of messages from sub-agent execution

        Returns:
            Extracted result string
        """
        from langchain_core.messages import AIMessage, HumanMessage

        tool_results = []
        ai_response = None

        for msg in messages:
            # Collect tool results (HumanMessage with name = tool name)
            if isinstance(msg, HumanMessage) and hasattr(msg, 'name') and msg.name:
                tool_results.append(msg.content)
            # Record last AI response without tool_calls
            elif isinstance(msg, AIMessage) and msg.content and not getattr(msg, 'tool_calls', None):
                ai_response = msg.content

        # Priority: AI summary > tool results > last message
        if ai_response:
            return ai_response
        elif tool_results:
            return "\n\n".join(tool_results)
        else:
            return messages[-1].content if messages else "No result"

    async def execute(
        self,
        task: str,
        context: str = "",
        agent_id: str = None
    ) -> str:
        # Generate agent ID if not provided
        if not agent_id:
            agent_id = generate_agent_id("subagent")

        # Create sub-agent task with full tool loop
        async def subagent_task(progress_callback=None):
            from ..agent.graph import build_agent_graph_no_checkpoint
            from ..tools.file_ops import set_current_agent, set_subagent_mode
            from langchain_core.messages import AIMessage

            # Set current agent ID for file locking
            set_current_agent(agent_id)
            # Set sub-agent mode - disables path confirmation prompts
            set_subagent_mode(True)

            if progress_callback:
                await progress_callback(0.1, "Starting sub-agent")

            # Get specialized prompt
            prompt = get_subagent_prompt(task, context)

            if progress_callback:
                await progress_callback(0.3, "Processing task")

            try:
                # Use full graph with tool loop
                graph = build_agent_graph_no_checkpoint()

                # CRITICAL: Mark as subagent and limit allowed tools
                # Sub-agents cannot spawn more agents (prevent infinite recursion)
                subagent_allowed_tools = [
                    "read_file", "write_file", "edit_file",
                    "list_dir", "search_files", "search_content",
                    "web_search"
                ]

                state = create_initial_state(
                    prompt,
                    thread_id=agent_id,
                    is_subagent=True,
                    allowed_tools=subagent_allowed_tools
                )

                # Add timeout to prevent hanging
                try:
                    result = await asyncio.wait_for(
                        graph.ainvoke(state, config={"recursion_limit": 50}),
                        timeout=180  # 180 second timeout
                    )
                except asyncio.TimeoutError:
                    return "Error: Sub-agent execution timed out after 180 seconds"

                if progress_callback:
                    await progress_callback(1.0, "Task complete")

                # Extract final response from messages
                # Priority: AI summary > tool results > last message
                messages = result.get("messages", [])
                return self._extract_subagent_result(messages)

            except Exception as e:
                if progress_callback:
                    await progress_callback(1.0, f"Error: {e}")
                return f"Error: {e}"

            finally:
                # Reset sub-agent mode when task completes
                set_subagent_mode(False)

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

        logger.info("Spawning agents in parallel", count=len(tasks))
        start_time = time.time()

        # Create all agent tasks FIRST
        agent_tasks = []
        agent_ids = []

        for i, task in enumerate(tasks):
            agent_id = f"parallel_{i}_{datetime.now().strftime('%H%M%S')}"
            agent_ids.append(agent_id)

            # Create the coroutine for this agent
            agent_tasks.append(self._run_agent_task(agent_id, task))

        # Launch ALL agents at the SAME time
        logger.debug("Launching all agents simultaneously", count=len(agent_tasks))
        results = await asyncio.gather(*agent_tasks, return_exceptions=True)

        elapsed = time.time() - start_time
        logger.info("All agents completed", count=len(tasks), elapsed=elapsed)

        # Build response
        lines = [f"Spawned {len(agent_ids)} parallel agents in {elapsed:.2f}s:"]
        for i, (agent_id, result) in enumerate(zip(agent_ids, results)):
            if isinstance(result, Exception):
                lines.append(f"  - {agent_id}: FAILED - {result}")
            else:
                lines.append(f"  - {agent_id}: COMPLETED")

        return "\n".join(lines)

    async def _run_agent_task(self, agent_id: str, task: str):
        """Run a single agent task with logging."""
        from ..agent.graph import build_agent_graph_no_checkpoint
        from ..tools.file_ops import set_current_agent, set_subagent_mode
        from langchain_core.messages import AIMessage

        logger.debug("Agent started", agent_id=agent_id, task_preview=task[:50])

        # Set current agent ID for file locking
        set_current_agent(agent_id)
        # Set sub-agent mode - disables path confirmation prompts
        set_subagent_mode(True)

        try:
            graph = build_agent_graph_no_checkpoint()

            subagent_allowed_tools = [
                "read_file", "write_file", "edit_file",
                "list_dir", "search_files", "search_content",
                "web_search"
            ]

            state = create_initial_state(
                task,
                thread_id=agent_id,
                is_subagent=True,
                allowed_tools=subagent_allowed_tools
            )

            task_start = time.time()
            result = await asyncio.wait_for(
                graph.ainvoke(state),
                timeout=180
            )
            task_elapsed = time.time() - task_start

            logger.debug("Agent completed", agent_id=agent_id, elapsed=task_elapsed)

            # Extract final response using improved logic
            messages = result.get("messages", [])
            return self._extract_subagent_result(messages)

        except asyncio.TimeoutError:
            logger.warning("Agent timeout", agent_id=agent_id)
            return "Error: Sub-agent execution timed out after 180 seconds"
        except Exception as e:
            logger.error("Agent failed", agent_id=agent_id, error=str(e))
            return f"Error: {e}"
        finally:
            # Reset sub-agent mode when task completes
            set_subagent_mode(False)


# Register agent tools
register_tool(SpawnAgentTool())
register_tool(ListAgentsTool())
register_tool(GetResultTool())
register_tool(SpawnParallelTool())
