"""Agent state definition."""

from typing import TypedDict, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """State for the main agent graph."""

    # Conversation
    messages: List[BaseMessage]  # Full conversation history

    # Task tracking
    current_task: Optional[str]           # Current user request
    plan: Optional[List[str]]             # Execution plan

    # Tool execution
    tool_results: List[dict]              # Results from tool calls
    pending_tool_calls: Optional[List[dict]]  # Tools waiting to be executed

    # Sub-agent management
    sub_agents: Dict[str, str]            # agent_id -> status
    sub_agent_results: Dict[str, Any]     # agent_id -> result

    # Control flow
    iteration: int                        # Current iteration count
    should_continue: bool                 # Whether to continue the loop
    thread_id: str                        # Session identifier

    # Error handling
    errors: Optional[List[str]]           # Accumulated errors

    # Sub-agent mode
    is_subagent: bool                     # Whether this is a sub-agent
    allowed_tools: Optional[List[str]]    # Tools allowed for this agent

    # Multi-file project tracking
    incomplete_check_count: int           # Count of consecutive incomplete checks
    last_missing_files: Optional[List[str]]  # Last detected missing files

    # Read-only tool loop detection (for auto-stop)
    consecutive_read_only_count: int      # Consecutive read-only tool calls
    last_tool_names: Optional[List[str]]  # Last executed tool names


def create_initial_state(
    user_input: str,
    history: Optional[List[BaseMessage]] = None,
    thread_id: str = "default",
    is_subagent: bool = False,
    allowed_tools: Optional[List[str]] = None
) -> AgentState:
    """Create initial state for a new conversation."""
    from langchain_core.messages import HumanMessage

    # Build messages from history + new input
    messages = list(history) if history else []
    messages.append(HumanMessage(content=user_input))

    return AgentState(
        messages=messages,
        current_task=user_input,
        plan=None,
        tool_results=[],
        pending_tool_calls=None,
        sub_agents={},
        sub_agent_results={},
        iteration=0,
        should_continue=True,
        thread_id=thread_id,
        errors=None,
        is_subagent=is_subagent,
        allowed_tools=allowed_tools,
        incomplete_check_count=0,
        last_missing_files=None,
        consecutive_read_only_count=0,
        last_tool_names=None,
    )
