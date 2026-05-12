"""Tests for Application Context module.

Tests cover:
- Lazy initialization
- Thread safety
- Override and reset functionality
- Provider creation
"""

import threading
import time
from unittest.mock import MagicMock

from mini_claude.context import (
    ApplicationContext,
    get_context,
    reset_context,
    init_context,
    isolated_context,
    Lazy,
)


class TestLazy:
    """Tests for Lazy wrapper."""

    def test_lazy_initialization(self):
        """Test lazy initialization creates instance on demand."""
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return MagicMock()

        lazy = Lazy(factory)
        assert not lazy.is_initialized()

        # First access creates instance
        instance1 = lazy.get()
        assert call_count == 1
        assert lazy.is_initialized()

        # Second access returns same instance
        instance2 = lazy.get()
        assert call_count == 1  # Not called again
        assert instance1 is instance2

    def test_lazy_set_override(self):
        """Test setting instance directly."""
        lazy = Lazy(lambda: MagicMock(name="original"))
        mock = MagicMock(name="override")

        lazy.set(mock)
        assert lazy.get() is mock

    def test_lazy_reset(self):
        """Test resetting lazy instance."""
        lazy = Lazy(lambda: MagicMock())
        lazy.get()
        assert lazy.is_initialized()

        lazy.reset()
        assert not lazy.is_initialized()

    def test_lazy_thread_safety(self):
        """Test thread-safe initialization."""
        call_count = 0
        call_lock = threading.Lock()

        def factory():
            nonlocal call_count
            with call_lock:
                call_count += 1
            time.sleep(0.01)  # Simulate slow creation
            return MagicMock()

        lazy = Lazy(factory)
        threads = []
        results = []

        def get_instance():
            results.append(lazy.get())

        for _ in range(10):
            t = threading.Thread(target=get_instance)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All threads should get the same instance
        assert len(results) == 10
        assert all(r is results[0] for r in results)
        assert call_count == 1  # Only called once


class TestApplicationContext:
    """Tests for ApplicationContext."""

    def test_context_creation(self):
        """Test creating context creates all lazy wrappers."""
        ctx = ApplicationContext()

        # All lazy wrappers should exist but not be initialized
        status = ctx.is_initialized()
        assert all(v is False for v in status.values())

    def test_property_access(self):
        """Test accessing properties creates instances."""
        reset_context()
        ctx = get_context()

        # Access should create instance of correct type
        from mini_claude.monitoring.metrics import MetricsCollector

        instance = ctx.metrics_collector
        assert isinstance(instance, MetricsCollector)

    def test_property_override(self):
        """Test overriding properties."""
        ctx = ApplicationContext()

        mock_metrics = MagicMock(name="mock_metrics")
        ctx.metrics_collector = mock_metrics

        assert ctx.metrics_collector is mock_metrics

    def test_reset_clears_all(self):
        """Test reset clears all instances."""
        ctx = ApplicationContext()

        # Initialize some components
        ctx._metrics_collector._instance = MagicMock()
        ctx._alert_manager._instance = MagicMock()

        ctx.reset()

        assert not ctx._metrics_collector.is_initialized()
        assert not ctx._alert_manager.is_initialized()

    def test_current_agent_id(self):
        """Test current agent ID tracking."""
        ctx = ApplicationContext()

        assert ctx.current_agent_id == "main"

        ctx.current_agent_id = "subagent-1"
        assert ctx.current_agent_id == "subagent-1"

        ctx.reset()
        assert ctx.current_agent_id == "main"


class TestGlobalContext:
    """Tests for global context functions."""

    def test_get_context_singleton(self):
        """Test get_context returns same instance."""
        reset_context()

        ctx1 = get_context()
        ctx2 = get_context()

        assert ctx1 is ctx2

    def test_reset_context(self):
        """Test reset_context clears global instance."""
        ctx1 = get_context()
        reset_context()
        ctx2 = get_context()

        # After reset, should be a new instance
        assert ctx1 is not ctx2

    def test_init_context_with_overrides(self):
        """Test init_context with overrides."""
        reset_context()

        mock_metrics = MagicMock()
        ctx = init_context(metrics_collector=mock_metrics)

        assert ctx.metrics_collector is mock_metrics

    def test_isolated_context(self):
        """Test isolated context manager."""
        original_ctx = get_context()

        with isolated_context() as isolated:
            # Inside context, get_context returns isolated
            ctx = get_context()
            assert ctx is isolated
            assert ctx is not original_ctx

        # Outside context, original is restored
        ctx = get_context()
        assert ctx is original_ctx


class TestProviderIntegration:
    """Integration tests for providers."""

    def test_metrics_collector_creation(self):
        """Test creating metrics collector via context."""
        reset_context()
        ctx = get_context()

        from mini_claude.monitoring.metrics import MetricsCollector

        instance = ctx.metrics_collector
        assert isinstance(instance, MetricsCollector)

    def test_token_counter_creation(self):
        """Test creating token counter via context."""
        reset_context()
        ctx = get_context()

        from mini_claude.utils.token_manager import TokenCounter

        instance = ctx.token_counter
        assert isinstance(instance, TokenCounter)

    def test_multiple_components(self):
        """Test accessing multiple components."""
        reset_context()
        ctx = get_context()

        # Access several components (lazy initialization)
        _ = ctx.metrics_collector
        _ = ctx.token_counter
        _ = ctx.rate_limiter

        # All should be initialized
        status = ctx.is_initialized()
        assert status["metrics_collector"]
        assert status["token_counter"]
        assert status["rate_limiter"]


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing code."""

    def test_context_provides_same_types(self):
        """Test that context provides same types as existing functions."""
        from mini_claude.monitoring.metrics import MetricsCollector, get_metrics_collector

        reset_context()

        # Get via context
        ctx = get_context()
        ctx_metrics = ctx.metrics_collector

        # Get via existing function
        func_metrics = get_metrics_collector()

        # Both should be the same type
        assert type(ctx_metrics) is type(func_metrics)
        assert isinstance(ctx_metrics, MetricsCollector)
        assert isinstance(func_metrics, MetricsCollector)

    def test_reset_functions_compatible(self):
        """Test that existing reset functions work with context."""
        from mini_claude.monitoring.metrics import (
            reset_metrics_collector,
        )

        reset_context()

        # Get via context
        ctx = get_context()
        ctx.metrics_collector  # Initialize

        # Reset via existing function
        reset_metrics_collector()

        # Context should now return None (or new instance)
        # This tests backward compatibility
