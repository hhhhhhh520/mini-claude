"""Provider factory functions for creating singleton instances.

Each provider function creates and configures a specific component.
These are used by ApplicationContext for lazy initialization.

Provider functions should:
1. Have no side effects when called
2. Return a properly configured instance
3. Handle missing dependencies gracefully
"""

from typing import Any, Dict, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from mini_claude.monitoring.metrics import MetricsCollector
    from mini_claude.monitoring.alerts import AlertManager
    from mini_claude.monitoring.health import HealthChecker
    from mini_claude.monitoring.tracing import TracingManager
    from mini_claude.tools.health_check import ToolHealthChecker
    from mini_claude.tools.cache import ToolCache
    from mini_claude.tools.dependencies import DependencyGraph
    from mini_claude.utils.session import SessionManager
    from mini_claude.utils.token_manager import TokenCounter
    from mini_claude.utils.safety import RateLimiter
    from mini_claude.utils.enhanced_memory import EnhancedMemoryManager
    from mini_claude.utils.logger import OutputSanitizer, AuditLogger, ExecutionLogExporter
    from mini_claude.config.watcher import ConfigFileWatcher
    from mini_claude.agent.graph import StateGraph
    from mini_claude.agent.suggestion import SuggestionEngine
    from mini_claude.agent.degradation import DegradationManager
    from mini_claude.cli.commands.base import CommandRegistry

logger = logging.getLogger(__name__)


class ProviderFactory:
    """Factory for creating provider functions with custom settings.

    Allows customization of provider creation for different environments
    (production, testing, development).
    """

    def __init__(self, settings_overrides: Optional[Dict[str, Any]] = None):
        """Initialize factory with optional settings overrides.

        Args:
            settings_overrides: Dict of settings to override.
        """
        self._settings_overrides = settings_overrides or {}

    def get_setting(self, name: str, default: Any = None) -> Any:
        """Get a setting value, checking overrides first.

        Args:
            name: Setting name.
            default: Default value if not found.

        Returns:
            The setting value.
        """
        if name in self._settings_overrides:
            return self._settings_overrides[name]

        from mini_claude.config.settings import settings
        return getattr(settings, name, default)


# =============================================================================
# Core Monitoring Providers
# =============================================================================

def create_metrics_collector() -> "MetricsCollector":
    """Create a MetricsCollector instance.

    Returns:
        Configured MetricsCollector.
    """
    from mini_claude.monitoring.metrics import MetricsCollector
    instance = MetricsCollector()
    logger.debug("provider_created", extra={"component": "metrics_collector"})
    return instance


def create_alert_manager() -> "AlertManager":
    """Create an AlertManager instance with configured rules.

    Returns:
        Configured AlertManager.
    """
    from mini_claude.monitoring.alerts import (
        AlertManager,
        HighFailureRateRule,
        HighLatencyRule,
        TokenBudgetRule,
        ToolFailureRule,
        LogHandler,
        WebhookHandler,
    )
    from mini_claude.config.settings import settings

    instance = AlertManager()

    # Add built-in rules based on settings
    if settings.alert_enabled:
        instance.add_rule(
            HighFailureRateRule(threshold=settings.alert_failure_rate_threshold)
        )
        instance.add_rule(
            HighLatencyRule(threshold=settings.alert_latency_threshold_seconds)
        )
        instance.add_rule(
            TokenBudgetRule(threshold=settings.alert_token_budget_threshold)
        )
        instance.add_rule(ToolFailureRule())

        # Add default handlers
        instance.add_handler(LogHandler())

        # Add webhook handler if configured
        if settings.alert_webhook_url:
            instance.add_handler(
                WebhookHandler(webhook_url=settings.alert_webhook_url)
            )

    logger.debug("provider_created", extra={
        "component": "alert_manager",
        "enabled": settings.alert_enabled,
    })
    return instance


def create_health_checker() -> "HealthChecker":
    """Create a HealthChecker instance.

    Returns:
        Configured HealthChecker.
    """
    from mini_claude.monitoring.health import HealthChecker
    instance = HealthChecker()
    logger.debug("provider_created", extra={"component": "health_checker"})
    return instance


def create_tool_health_checker() -> "ToolHealthChecker":
    """Create a ToolHealthChecker instance.

    Returns:
        Configured ToolHealthChecker.
    """
    from mini_claude.tools.health_check import ToolHealthChecker
    instance = ToolHealthChecker()
    logger.debug("provider_created", extra={"component": "tool_health_checker"})
    return instance


def create_tracing_manager() -> "TracingManager":
    """Create a TracingManager instance.

    Returns:
        Configured TracingManager.
    """
    from mini_claude.monitoring.tracing import TracingManager
    from mini_claude.config.settings import settings

    instance = TracingManager()

    # Auto-setup if enabled in settings
    if settings.tracing_enabled:
        instance.setup()

    logger.debug("provider_created", extra={
        "component": "tracing_manager",
        "enabled": settings.tracing_enabled,
    })
    return instance


# =============================================================================
# Session and State Providers
# =============================================================================

def create_session_manager() -> "SessionManager":
    """Create a SessionManager instance.

    Returns:
        Configured SessionManager.
    """
    from mini_claude.utils.session import SessionManager
    from mini_claude.config.settings import settings

    db_path = getattr(settings, "session_db_path", "sessions.db")
    instance = SessionManager(db_path)
    logger.debug("provider_created", extra={
        "component": "session_manager",
        "db_path": db_path,
    })
    return instance


def create_token_counter() -> "TokenCounter":
    """Create a TokenCounter instance.

    Returns:
        Configured TokenCounter.
    """
    from mini_claude.utils.token_manager import TokenCounter
    from mini_claude.config.settings import settings

    model = settings.default_model
    instance = TokenCounter(model=model)
    logger.debug("provider_created", extra={
        "component": "token_counter",
        "model": model,
    })
    return instance


def create_enhanced_memory_manager() -> "EnhancedMemoryManager":
    """Create an EnhancedMemoryManager instance.

    Returns:
        Configured EnhancedMemoryManager.

    Raises:
        DependencyNotFoundError: If required dependencies are not installed.
    """
    from mini_claude.utils.enhanced_memory import EnhancedMemoryManager
    from mini_claude.config.settings import settings

    vector_store_path = getattr(settings, "vector_store_path", "vector_store")
    session_db_path = getattr(settings, "session_db_path", "sessions.db")

    instance = EnhancedMemoryManager(
        vector_store_path=vector_store_path,
        session_db_path=session_db_path,
    )
    logger.debug("provider_created", extra={"component": "enhanced_memory_manager"})
    return instance


# =============================================================================
# Tools Providers
# =============================================================================

def create_tool_cache() -> "ToolCache":
    """Create a ToolCache instance.

    Returns:
        Configured ToolCache.
    """
    from mini_claude.tools.cache import ToolCache
    from mini_claude.config.settings import settings

    instance = ToolCache(
        ttl_seconds=settings.tool_cache_ttl_seconds,
        max_size=settings.tool_cache_max_size,
        cacheable_tools=settings.tool_cache_tools,
    )
    logger.debug("provider_created", extra={
        "component": "tool_cache",
        "ttl_seconds": settings.tool_cache_ttl_seconds,
        "max_size": settings.tool_cache_max_size,
    })
    return instance


def create_dependency_graph() -> "DependencyGraph":
    """Create a DependencyGraph instance with builtin dependencies.

    Returns:
        Configured DependencyGraph.
    """
    from mini_claude.tools.dependencies import DependencyGraph, ToolDependency

    instance = DependencyGraph()

    # Initialize builtin dependencies
    # edit_file depends on read_file (need to read before editing)
    instance.add_dependency(ToolDependency(
        tool_name="edit_file",
        depends_on=["read_file"],
        optional=False,
        description="edit_file requires reading file content first to find text to replace",
    ))

    # force_write optionally depends on read_file (for conflict detection context)
    instance.add_dependency(ToolDependency(
        tool_name="force_write",
        depends_on=["read_file"],
        optional=True,
        description="force_write can benefit from read_file context for conflict detection",
    ))

    logger.debug("provider_created", extra={"component": "dependency_graph"})
    return instance


def create_rate_limiter() -> "RateLimiter":
    """Create a RateLimiter instance.

    Returns:
        Configured RateLimiter.
    """
    from mini_claude.utils.safety import RateLimiter
    from mini_claude.config.settings import settings

    instance = RateLimiter(
        requests_per_minute=settings.rate_limit_requests_per_minute,
        strategy=settings.rate_limit_strategy,
        burst_size=settings.rate_limit_burst_size,
        enabled=settings.rate_limit_enabled,
    )
    logger.debug("provider_created", extra={
        "component": "rate_limiter",
        "requests_per_minute": settings.rate_limit_requests_per_minute,
        "enabled": settings.rate_limit_enabled,
    })
    return instance


# =============================================================================
# Agent Providers
# =============================================================================

def create_agent_graph() -> "StateGraph":
    """Create an agent graph instance.

    Returns:
        Configured StateGraph.
    """
    from mini_claude.agent.graph import build_agent_graph

    instance = build_agent_graph()
    logger.debug("provider_created", extra={"component": "agent_graph"})
    return instance


def create_suggestion_engine() -> "SuggestionEngine":
    """Create a SuggestionEngine instance.

    Returns:
        Configured SuggestionEngine.
    """
    from mini_claude.agent.suggestion import SuggestionEngine
    from mini_claude.config.settings import settings

    language = getattr(settings, "suggestion_language", "zh")
    instance = SuggestionEngine(language=language)
    logger.debug("provider_created", extra={
        "component": "suggestion_engine",
        "language": language,
    })
    return instance


def create_degradation_manager() -> "DegradationManager":
    """Create a DegradationManager instance.

    Returns:
        Configured DegradationManager.
    """
    from mini_claude.agent.degradation import DegradationManager
    from mini_claude.config.settings import settings

    config = {
        "model": {
            "primary": settings.default_model,
            "fallbacks": [],
        },
        "backoff": {
            "max_retries": 3,
        },
        "tool": {
            "max_failures": 3,
        },
        "strategy": {
            "initial_strategy": "react",
        },
    }
    instance = DegradationManager(config)
    logger.debug("provider_created", extra={"component": "degradation_manager"})
    return instance


# =============================================================================
# Config Providers
# =============================================================================

def create_config_watcher() -> "ConfigFileWatcher":
    """Create a ConfigFileWatcher instance.

    Returns:
        Configured ConfigFileWatcher.
    """
    from mini_claude.config.watcher import ConfigFileWatcher
    from mini_claude.config.settings import settings

    instance = ConfigFileWatcher(settings=settings)
    logger.debug("provider_created", extra={"component": "config_watcher"})
    return instance


# =============================================================================
# Logging Providers
# =============================================================================

def create_output_sanitizer() -> "OutputSanitizer":
    """Create an OutputSanitizer instance.

    Returns:
        Configured OutputSanitizer.
    """
    from mini_claude.utils.logger import OutputSanitizer

    instance = OutputSanitizer()
    logger.debug("provider_created", extra={"component": "output_sanitizer"})
    return instance


def create_audit_logger() -> "AuditLogger":
    """Create an AuditLogger instance.

    Returns:
        Configured AuditLogger.

    Note:
        This requires logging to be initialized first.
        May return None if not initialized.
    """
    from mini_claude.utils.logger import get_audit_logger

    instance = get_audit_logger()
    logger.debug("provider_created", extra={
        "component": "audit_logger",
        "initialized": instance is not None,
    })
    return instance


def create_execution_log_exporter() -> "ExecutionLogExporter":
    """Create an ExecutionLogExporter instance.

    Returns:
        Configured ExecutionLogExporter.
    """
    from mini_claude.utils.logger import ExecutionLogExporter

    instance = ExecutionLogExporter(sanitize_output=True)
    logger.debug("provider_created", extra={"component": "execution_log_exporter"})
    return instance


# =============================================================================
# CLI Providers
# =============================================================================

def create_command_registry() -> "CommandRegistry":
    """Create a CommandRegistry instance with all handlers registered.

    Returns:
        Configured CommandRegistry.
    """
    from mini_claude.cli.commands.base import CommandRegistry
    from mini_claude.cli.commands import (
        profile_handler,
        session_handler,
        metrics_handler,
        cache_handler,
        config_handler,
        log_handler,
        alert_handler,
        help_handler,
    )

    instance = CommandRegistry()

    # Register all handlers
    for handler_class in [
        profile_handler.ProfileCommandHandler,
        session_handler.SessionCommandHandler,
        metrics_handler.MetricsCommandHandler,
        cache_handler.CacheCommandHandler,
        config_handler.ConfigCommandHandler,
        log_handler.LogCommandHandler,
        alert_handler.AlertCommandHandler,
        help_handler.HelpCommandHandler,
    ]:
        instance.register(handler_class())

    logger.debug("provider_created", extra={"component": "command_registry"})
    return instance


# =============================================================================
# Agent Context Providers
# =============================================================================

def create_current_agent_context() -> str:
    """Create the current agent context.

    Returns:
        Default agent ID.
    """
    return "main"


# =============================================================================
# Convenience Functions
# =============================================================================

def create_all_providers() -> Dict[str, Any]:
    """Create all provider instances.

    Useful for initialization or testing.

    Returns:
        Dict mapping component names to instances.
    """
    return {
        "metrics_collector": create_metrics_collector(),
        "alert_manager": create_alert_manager(),
        "session_manager": create_session_manager(),
        "token_counter": create_token_counter(),
        "health_checker": create_health_checker(),
        "tool_health_checker": create_tool_health_checker(),
        "tracing_manager": create_tracing_manager(),
        "tool_cache": create_tool_cache(),
        "rate_limiter": create_rate_limiter(),
        "dependency_graph": create_dependency_graph(),
        "agent_graph": create_agent_graph(),
        "suggestion_engine": create_suggestion_engine(),
        "degradation_manager": create_degradation_manager(),
        "config_watcher": create_config_watcher(),
        "output_sanitizer": create_output_sanitizer(),
        "execution_log_exporter": create_execution_log_exporter(),
        "command_registry": create_command_registry(),
    }
