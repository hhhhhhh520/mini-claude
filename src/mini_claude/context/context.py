"""Application Context - centralized container for singleton instances.

This module provides a dependency injection container that:
1. Encapsulates all singleton instances
2. Enables testability through easy mocking
3. Provides lazy initialization
4. Supports context isolation for tests

Usage:
    from mini_claude.context import get_context

    # Get singleton instance
    metrics = get_context().metrics_collector

    # In tests, use override
    ctx = ApplicationContext()
    ctx.metrics_collector = mock_metrics
    ctx.__enter__()
    # ... test code ...
    ctx.__exit__()
"""

from contextlib import contextmanager
from typing import (
    Callable,
    Dict,
    Optional,
    TypeVar,
    Generic,
    TYPE_CHECKING,
)
import threading
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

T = TypeVar("T")


class Lazy(Generic[T]):
    """Lazy initialization wrapper for singleton instances.

    Provides on-demand creation with thread-safety.
    """

    def __init__(self, factory: Callable[[], T]):
        """Initialize lazy wrapper.

        Args:
            factory: Function to create the instance when needed.
        """
        self._factory = factory
        self._instance: Optional[T] = None
        self._lock = threading.Lock()

    def get(self) -> T:
        """Get or create the instance.

        Returns:
            The singleton instance.
        """
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self._instance = self._factory()
        return self._instance

    def set(self, instance: Optional[T]) -> None:
        """Set or override the instance.

        Args:
            instance: The instance to set, or None to reset.
        """
        with self._lock:
            self._instance = instance

    def is_initialized(self) -> bool:
        """Check if instance has been created.

        Returns:
            True if instance exists.
        """
        return self._instance is not None

    def reset(self) -> None:
        """Reset the instance to None."""
        with self._lock:
            self._instance = None


class ApplicationContext:
    """Centralized container for application-wide singleton instances.

    Features:
    - Lazy initialization of all components
    - Thread-safe singleton access
    - Easy mocking for tests
    - Context manager support for test isolation
    - Component lifecycle management

    Example:
        # Normal usage
        ctx = ApplicationContext()
        metrics = ctx.metrics_collector

        # With overrides for testing
        ctx = ApplicationContext()
        ctx._metrics_collector.set(mock_metrics)
        with ctx.override():
            # All code using get_context() gets the mock
            pass
    """

    def __init__(self) -> None:
        """Initialize the application context with lazy providers."""
        # Import providers lazily to avoid circular imports
        from .providers import (
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
        )

        # Core monitoring
        self._metrics_collector: Lazy["MetricsCollector"] = Lazy(create_metrics_collector)
        self._alert_manager: Lazy["AlertManager"] = Lazy(create_alert_manager)
        self._health_checker: Lazy["HealthChecker"] = Lazy(create_health_checker)
        self._tool_health_checker: Lazy["ToolHealthChecker"] = Lazy(create_tool_health_checker)
        self._tracing_manager: Lazy["TracingManager"] = Lazy(create_tracing_manager)

        # Session and state
        self._session_manager: Lazy["SessionManager"] = Lazy(create_session_manager)
        self._token_counter: Lazy["TokenCounter"] = Lazy(create_token_counter)
        self._enhanced_memory_manager: Lazy["EnhancedMemoryManager"] = Lazy(
            create_enhanced_memory_manager
        )

        # Tools
        self._tool_cache: Lazy["ToolCache"] = Lazy(create_tool_cache)
        self._dependency_graph: Lazy["DependencyGraph"] = Lazy(create_dependency_graph)
        self._rate_limiter: Lazy["RateLimiter"] = Lazy(create_rate_limiter)

        # Agent
        self._agent_graph: Lazy["StateGraph"] = Lazy(create_agent_graph)
        self._suggestion_engine: Lazy["SuggestionEngine"] = Lazy(create_suggestion_engine)
        self._degradation_manager: Lazy["DegradationManager"] = Lazy(create_degradation_manager)

        # Config
        self._config_watcher: Lazy["ConfigFileWatcher"] = Lazy(create_config_watcher)

        # Logging
        self._output_sanitizer: Lazy["OutputSanitizer"] = Lazy(create_output_sanitizer)
        self._audit_logger: Lazy["AuditLogger"] = Lazy(create_audit_logger)
        self._execution_log_exporter: Lazy["ExecutionLogExporter"] = Lazy(
            create_execution_log_exporter
        )

        # CLI
        self._command_registry: Lazy["CommandRegistry"] = Lazy(create_command_registry)

        # Agent context
        self._current_agent_id: str = "main"

        # Override stack for nested contexts
        self._override_stack: list = []

    # -------------------------------------------------------------------------
    # Properties - Core Monitoring
    # -------------------------------------------------------------------------

    @property
    def metrics_collector(self) -> "MetricsCollector":
        """Get the metrics collector instance."""
        return self._metrics_collector.get()

    @metrics_collector.setter
    def metrics_collector(self, value: Optional["MetricsCollector"]) -> None:
        """Set or override the metrics collector."""
        self._metrics_collector.set(value)

    @property
    def alert_manager(self) -> "AlertManager":
        """Get the alert manager instance."""
        return self._alert_manager.get()

    @alert_manager.setter
    def alert_manager(self, value: Optional["AlertManager"]) -> None:
        """Set or override the alert manager."""
        self._alert_manager.set(value)

    @property
    def health_checker(self) -> "HealthChecker":
        """Get the health checker instance."""
        return self._health_checker.get()

    @health_checker.setter
    def health_checker(self, value: Optional["HealthChecker"]) -> None:
        """Set or override the health checker."""
        self._health_checker.set(value)

    @property
    def tool_health_checker(self) -> "ToolHealthChecker":
        """Get the tool health checker instance."""
        return self._tool_health_checker.get()

    @tool_health_checker.setter
    def tool_health_checker(self, value: Optional["ToolHealthChecker"]) -> None:
        """Set or override the tool health checker."""
        self._tool_health_checker.set(value)

    @property
    def tracing_manager(self) -> "TracingManager":
        """Get the tracing manager instance."""
        return self._tracing_manager.get()

    @tracing_manager.setter
    def tracing_manager(self, value: Optional["TracingManager"]) -> None:
        """Set or override the tracing manager."""
        self._tracing_manager.set(value)

    # -------------------------------------------------------------------------
    # Properties - Session and State
    # -------------------------------------------------------------------------

    @property
    def session_manager(self) -> "SessionManager":
        """Get the session manager instance."""
        return self._session_manager.get()

    @session_manager.setter
    def session_manager(self, value: Optional["SessionManager"]) -> None:
        """Set or override the session manager."""
        self._session_manager.set(value)

    @property
    def token_counter(self) -> "TokenCounter":
        """Get the token counter instance."""
        return self._token_counter.get()

    @token_counter.setter
    def token_counter(self, value: Optional["TokenCounter"]) -> None:
        """Set or override the token counter."""
        self._token_counter.set(value)

    @property
    def enhanced_memory_manager(self) -> "EnhancedMemoryManager":
        """Get the enhanced memory manager instance."""
        return self._enhanced_memory_manager.get()

    @enhanced_memory_manager.setter
    def enhanced_memory_manager(self, value: Optional["EnhancedMemoryManager"]) -> None:
        """Set or override the enhanced memory manager."""
        self._enhanced_memory_manager.set(value)

    # -------------------------------------------------------------------------
    # Properties - Tools
    # -------------------------------------------------------------------------

    @property
    def tool_cache(self) -> "ToolCache":
        """Get the tool cache instance."""
        return self._tool_cache.get()

    @tool_cache.setter
    def tool_cache(self, value: Optional["ToolCache"]) -> None:
        """Set or override the tool cache."""
        self._tool_cache.set(value)

    @property
    def dependency_graph(self) -> "DependencyGraph":
        """Get the dependency graph instance."""
        return self._dependency_graph.get()

    @dependency_graph.setter
    def dependency_graph(self, value: Optional["DependencyGraph"]) -> None:
        """Set or override the dependency graph."""
        self._dependency_graph.set(value)

    @property
    def rate_limiter(self) -> "RateLimiter":
        """Get the rate limiter instance."""
        return self._rate_limiter.get()

    @rate_limiter.setter
    def rate_limiter(self, value: Optional["RateLimiter"]) -> None:
        """Set or override the rate limiter."""
        self._rate_limiter.set(value)

    # -------------------------------------------------------------------------
    # Properties - Agent
    # -------------------------------------------------------------------------

    @property
    def agent_graph(self) -> "StateGraph":
        """Get the agent graph instance."""
        return self._agent_graph.get()

    @agent_graph.setter
    def agent_graph(self, value: Optional["StateGraph"]) -> None:
        """Set or override the agent graph."""
        self._agent_graph.set(value)

    @property
    def suggestion_engine(self) -> "SuggestionEngine":
        """Get the suggestion engine instance."""
        return self._suggestion_engine.get()

    @suggestion_engine.setter
    def suggestion_engine(self, value: Optional["SuggestionEngine"]) -> None:
        """Set or override the suggestion engine."""
        self._suggestion_engine.set(value)

    @property
    def degradation_manager(self) -> "DegradationManager":
        """Get the degradation manager instance."""
        return self._degradation_manager.get()

    @degradation_manager.setter
    def degradation_manager(self, value: Optional["DegradationManager"]) -> None:
        """Set or override the degradation manager."""
        self._degradation_manager.set(value)

    # -------------------------------------------------------------------------
    # Properties - Config
    # -------------------------------------------------------------------------

    @property
    def config_watcher(self) -> "ConfigFileWatcher":
        """Get the config watcher instance."""
        return self._config_watcher.get()

    @config_watcher.setter
    def config_watcher(self, value: Optional["ConfigFileWatcher"]) -> None:
        """Set or override the config watcher."""
        self._config_watcher.set(value)

    # -------------------------------------------------------------------------
    # Properties - Logging
    # -------------------------------------------------------------------------

    @property
    def output_sanitizer(self) -> "OutputSanitizer":
        """Get the output sanitizer instance."""
        return self._output_sanitizer.get()

    @output_sanitizer.setter
    def output_sanitizer(self, value: Optional["OutputSanitizer"]) -> None:
        """Set or override the output sanitizer."""
        self._output_sanitizer.set(value)

    @property
    def audit_logger(self) -> "AuditLogger":
        """Get the audit logger instance."""
        return self._audit_logger.get()

    @audit_logger.setter
    def audit_logger(self, value: Optional["AuditLogger"]) -> None:
        """Set or override the audit logger."""
        self._audit_logger.set(value)

    @property
    def execution_log_exporter(self) -> "ExecutionLogExporter":
        """Get the execution log exporter instance."""
        return self._execution_log_exporter.get()

    @execution_log_exporter.setter
    def execution_log_exporter(self, value: Optional["ExecutionLogExporter"]) -> None:
        """Set or override the execution log exporter."""
        self._execution_log_exporter.set(value)

    # -------------------------------------------------------------------------
    # Properties - CLI
    # -------------------------------------------------------------------------

    @property
    def command_registry(self) -> "CommandRegistry":
        """Get the command registry instance."""
        return self._command_registry.get()

    @command_registry.setter
    def command_registry(self, value: Optional["CommandRegistry"]) -> None:
        """Set or override the command registry."""
        self._command_registry.set(value)

    # -------------------------------------------------------------------------
    # Properties - Agent Context
    # -------------------------------------------------------------------------

    @property
    def current_agent_id(self) -> str:
        """Get the current agent ID."""
        return self._current_agent_id

    @current_agent_id.setter
    def current_agent_id(self, value: str) -> None:
        """Set the current agent ID."""
        self._current_agent_id = value

    # -------------------------------------------------------------------------
    # Context Manager Support
    # -------------------------------------------------------------------------

    @contextmanager
    def override(self):
        """Context manager for test isolation.

        Saves current state and restores it on exit.

        Example:
            ctx = ApplicationContext()
            ctx.metrics_collector = mock_metrics
            with ctx.override():
                # test code
                pass
        """
        # Save current state
        state = {
            "_current_agent_id": self._current_agent_id,
        }
        self._override_stack.append(state)

        try:
            yield self
        finally:
            # Restore state
            if self._override_stack:
                saved = self._override_stack.pop()
                self._current_agent_id = saved["_current_agent_id"]

    def reset(self) -> None:
        """Reset all lazy instances to None.

        Useful for testing and cleanup.
        """
        lazy_attrs = [
            "_metrics_collector",
            "_alert_manager",
            "_health_checker",
            "_tool_health_checker",
            "_tracing_manager",
            "_session_manager",
            "_token_counter",
            "_enhanced_memory_manager",
            "_tool_cache",
            "_dependency_graph",
            "_rate_limiter",
            "_agent_graph",
            "_suggestion_engine",
            "_degradation_manager",
            "_config_watcher",
            "_output_sanitizer",
            "_audit_logger",
            "_execution_log_exporter",
            "_command_registry",
        ]
        for attr in lazy_attrs:
            lazy = getattr(self, attr, None)
            if isinstance(lazy, Lazy):
                lazy.reset()

        self._current_agent_id = "main"

    def is_initialized(self) -> Dict[str, bool]:
        """Check which components have been initialized.

        Returns:
            Dict mapping component names to their initialization status.
        """
        return {
            "metrics_collector": self._metrics_collector.is_initialized(),
            "alert_manager": self._alert_manager.is_initialized(),
            "health_checker": self._health_checker.is_initialized(),
            "tool_health_checker": self._tool_health_checker.is_initialized(),
            "tracing_manager": self._tracing_manager.is_initialized(),
            "session_manager": self._session_manager.is_initialized(),
            "token_counter": self._token_counter.is_initialized(),
            "enhanced_memory_manager": self._enhanced_memory_manager.is_initialized(),
            "tool_cache": self._tool_cache.is_initialized(),
            "dependency_graph": self._dependency_graph.is_initialized(),
            "rate_limiter": self._rate_limiter.is_initialized(),
            "agent_graph": self._agent_graph.is_initialized(),
            "suggestion_engine": self._suggestion_engine.is_initialized(),
            "degradation_manager": self._degradation_manager.is_initialized(),
            "config_watcher": self._config_watcher.is_initialized(),
            "output_sanitizer": self._output_sanitizer.is_initialized(),
            "audit_logger": self._audit_logger.is_initialized(),
            "execution_log_exporter": self._execution_log_exporter.is_initialized(),
            "command_registry": self._command_registry.is_initialized(),
        }


# =============================================================================
# Global Context Instance
# =============================================================================

_context: Optional[ApplicationContext] = None
_context_lock = threading.Lock()


def get_context() -> ApplicationContext:
    """Get the global application context.

    Creates the context on first call (lazy initialization).

    Returns:
        The singleton ApplicationContext instance.
    """
    global _context
    if _context is None:
        with _context_lock:
            if _context is None:
                _context = ApplicationContext()
                logger.debug("application_context_initialized")
    return _context


def reset_context() -> None:
    """Reset the global application context.

    Useful for testing and cleanup.
    """
    global _context
    with _context_lock:
        if _context is not None:
            _context.reset()
        _context = None


def init_context(**overrides) -> ApplicationContext:
    """Initialize the global context with optional overrides.

    Args:
        **overrides: Component instances to pre-set.

    Returns:
        The initialized ApplicationContext.

    Example:
        ctx = init_context(
            metrics_collector=mock_metrics,
            session_manager=mock_session,
        )
    """
    global _context
    with _context_lock:
        _context = ApplicationContext()
        for key, value in overrides.items():
            if hasattr(_context, key):
                setattr(_context, key, value)
            else:
                logger.warning(f"unknown_context_attribute: {key}")
    return _context


@contextmanager
def isolated_context():
    """Context manager for test isolation.

    Creates a fresh context and restores the original on exit.

    Example:
        with isolated_context():
            ctx = get_context()
            ctx.metrics_collector = mock_metrics
            # test code
    """
    global _context
    original = _context
    _context = None
    try:
        yield get_context()
    finally:
        _context = original
