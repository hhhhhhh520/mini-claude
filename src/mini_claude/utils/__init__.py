"""Utils module."""

from datetime import datetime

from mini_claude.utils.profile import UserProfile, UserProfileManager
from mini_claude.utils.vector_store import (
    VectorStore,
    SearchResult,
    Document,
    VectorStoreError,
    DependencyNotFoundError,
    check_vector_store_dependencies,
    get_recommended_backend,
)
from mini_claude.utils.enhanced_memory import (
    EnhancedMemoryManager,
    SessionSearchResult,
    get_enhanced_memory_manager,
)
from mini_claude.utils.safety import (
    RateLimiter,
    get_rate_limiter,
    reset_rate_limiter,
)


def generate_agent_id(prefix: str = "agent") -> str:
    """生成唯一的 Agent ID。

    Args:
        prefix: ID 前缀，如 'agent', 'subagent'

    Returns:
        格式为 '{prefix}_{HHMMSS}_{short_uuid}' 的唯一 ID
    """
    import uuid

    timestamp = datetime.now().strftime("%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    return f"{prefix}_{timestamp}_{short_id}"


__all__ = [
    "generate_agent_id",
    "UserProfile",
    "UserProfileManager",
    "VectorStore",
    "SearchResult",
    "Document",
    "VectorStoreError",
    "DependencyNotFoundError",
    "check_vector_store_dependencies",
    "get_recommended_backend",
    "EnhancedMemoryManager",
    "SessionSearchResult",
    "get_enhanced_memory_manager",
    "RateLimiter",
    "get_rate_limiter",
    "reset_rate_limiter",
]
