"""REPL helper utilities.

This module contains utility functions extracted from the REPL module
to keep the main REPL class focused on core loop logic.
"""

from typing import List, Any


def manage_message_history(
    messages: List[Any],
    max_messages: int = 50,
    default_model: str = "deepseek-chat",
) -> List[Any]:
    """Manage message history based on token count.

    Instead of fixed message limit, use token-based management.
    Falls back to message count limit if token counting fails.

    Args:
        messages: List of messages to manage
        max_messages: Maximum number of messages to keep (fallback limit)
        default_model: Model for token counting

    Returns:
        Managed message list
    """
    if len(messages) <= max_messages:
        return messages

    try:
        from ..utils.token_manager import get_token_counter
        from langchain_core.messages import HumanMessage

        token_counter = get_token_counter(default_model)

        # Convert to dict format for token counting
        messages_for_count = []
        for msg in messages:
            if isinstance(msg, dict):
                messages_for_count.append(msg)
            else:
                role = "user" if isinstance(msg, HumanMessage) else "assistant"
                content = msg.content if hasattr(msg, "content") else str(msg)
                messages_for_count.append({"role": role, "content": content})

        stats = token_counter.get_usage_stats(messages_for_count)

        # If within budget, keep all
        if not stats["is_over_budget"]:
            return messages

        # Need to trim - keep first (system) and last N messages
        keep_first = 1  # System message
        keep_last = min(20, len(messages) - keep_first)

        if len(messages) > keep_first + keep_last:
            return messages[:keep_first] + messages[-keep_last:]

    except Exception:
        pass

    # Fallback: keep last max_messages
    return messages[-max_messages:]
