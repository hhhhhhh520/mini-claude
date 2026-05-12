"""Application Context module.

Provides a centralized container for all singleton instances,
enabling dependency injection and testability.
"""

from .context import (
    ApplicationContext,
    get_context,
    reset_context,
    init_context,
    isolated_context,
    Lazy,
)
from .providers import (
    ProviderFactory,
    create_metrics_collector,
    create_alert_manager,
    create_session_manager,
    create_token_counter,
    create_health_checker,
    create_tool_health_checker,
    create_tracing_manager,
    create_tool_cache,
    create_rate_limiter,
    create_enhanced_memory_manager,
    create_dependency_graph,
    create_config_watcher,
    create_agent_graph,
    create_suggestion_engine,
    create_degradation_manager,
    create_output_sanitizer,
    create_audit_logger,
    create_execution_log_exporter,
    create_command_registry,
    create_current_agent_context,
)

__all__ = [
    # Context
    "ApplicationContext",
    "get_context",
    "reset_context",
    "init_context",
    "isolated_context",
    "Lazy",
    # Providers
    "ProviderFactory",
    "create_metrics_collector",
    "create_alert_manager",
    "create_session_manager",
    "create_token_counter",
    "create_health_checker",
    "create_tool_health_checker",
    "create_tracing_manager",
    "create_tool_cache",
    "create_rate_limiter",
    "create_enhanced_memory_manager",
    "create_dependency_graph",
    "create_config_watcher",
    "create_agent_graph",
    "create_suggestion_engine",
    "create_degradation_manager",
    "create_output_sanitizer",
    "create_audit_logger",
    "create_execution_log_exporter",
    "create_command_registry",
    "create_current_agent_context",
]
