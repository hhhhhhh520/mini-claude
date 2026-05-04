"""Prometheus metrics collection for Mini Claude Code.

Provides comprehensive observability for:
- Request counts (total, success, failed)
- Request latency distribution
- Token usage tracking
- Tool call statistics

Usage:
    from mini_claude.monitoring.metrics import get_metrics_collector

    collector = get_metrics_collector()

    # Record request
    collector.record_request_start()
    # ... do work ...
    collector.record_request_end(success=True, duration=0.5)

    # Get metrics output
    print(collector.get_metrics())
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Use prometheus-client for standard Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY

from mini_claude.config.settings import settings
from mini_claude.utils.logger import get_logger

logger = get_logger("mini_claude.monitoring.metrics")


# =============================================================================
# Metric Definitions
# =============================================================================

# Use default registry
_registry = REGISTRY

# Request counter - total requests processed
REQUESTS_TOTAL = Counter(
    "mini_claude_requests_total",
    "Total number of requests processed",
    registry=_registry,
)

# Request success counter
REQUESTS_SUCCESS = Counter(
    "mini_claude_requests_success",
    "Number of successful requests",
    registry=_registry,
)

# Request failure counter
REQUESTS_FAILED = Counter(
    "mini_claude_requests_failed",
    "Number of failed requests",
    ["error_type"],  # Label for error classification
    registry=_registry,
)

# Request duration histogram (in seconds)
REQUEST_DURATION = Histogram(
    "mini_claude_request_duration_seconds",
    "Request duration in seconds",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
    registry=_registry,
)

# Token usage counter
TOKEN_USAGE_TOTAL = Counter(
    "mini_claude_token_usage_total",
    "Total token usage",
    ["type"],  # 'input' or 'output'
    registry=_registry,
)

# Tool calls counter
TOOL_CALLS_TOTAL = Counter(
    "mini_claude_tool_calls_total",
    "Total number of tool calls",
    ["tool_name", "status"],  # Combined labels: tool name + 'success' or 'failure'
    registry=_registry,
)

# Current active requests gauge
ACTIVE_REQUESTS = Gauge(
    "mini_claude_active_requests",
    "Number of currently active requests",
    registry=_registry,
)

# Iteration counter per session
ITERATIONS_TOTAL = Counter(
    "mini_claude_iterations_total",
    "Total iterations across all requests",
    registry=_registry,
)


# =============================================================================
# Metrics Collector Class
# =============================================================================

@dataclass
class MetricSnapshot:
    """Snapshot of current metrics values."""

    requests_total: int = 0
    requests_success: int = 0
    requests_failed: int = 0
    active_requests: int = 0
    token_input: int = 0
    token_output: int = 0
    tool_calls_success: Dict[str, int] = field(default_factory=dict)
    tool_calls_failure: Dict[str, int] = field(default_factory=dict)
    duration_samples: int = 0
    duration_sum: float = 0.0


class MetricsCollector:
    """Centralized metrics collector for Mini Claude Code.

    Provides a clean API for recording metrics throughout the application.
    Thread-safe and can be used as a singleton.

    Example:
        collector = MetricsCollector()

        # Using context manager
        with collector.request_context():
            collector.record_token_usage(100, "input")
            collector.record_tool_call("write_file", success=True)

        # Get Prometheus output
        print(collector.get_metrics())
    """

    def __init__(self):
        """Initialize the metrics collector."""
        self._start_time = time.time()
        self._snapshot = MetricSnapshot()

    def record_request_start(self) -> float:
        """Record the start of a request.

        Returns:
            Start timestamp for duration calculation.
        """
        ACTIVE_REQUESTS.inc()
        self._snapshot.active_requests += 1
        logger.debug("metrics: request started")
        return time.time()

    def record_request_end(
        self,
        success: bool,
        duration: float,
        error_type: Optional[str] = None,
    ) -> None:
        """Record the end of a request.

        Args:
            success: Whether the request succeeded.
            duration: Request duration in seconds.
            error_type: Error classification if failed (e.g., "llm_error", "tool_error").
        """
        ACTIVE_REQUESTS.dec()
        self._snapshot.active_requests -= 1

        REQUESTS_TOTAL.inc()
        self._snapshot.requests_total += 1

        if success:
            REQUESTS_SUCCESS.inc()
            self._snapshot.requests_success += 1
        else:
            if error_type:
                REQUESTS_FAILED.labels(error_type=error_type).inc()
            else:
                REQUESTS_FAILED.labels(error_type="unknown").inc()
            self._snapshot.requests_failed += 1

        # Record duration
        REQUEST_DURATION.observe(duration)
        self._snapshot.duration_samples += 1
        self._snapshot.duration_sum += duration

        logger.debug(
            "metrics: request ended",
            success=success,
            duration=duration,
            error_type=error_type,
        )

    def record_token_usage(self, tokens: int, token_type: str = "input") -> None:
        """Record token usage.

        Args:
            tokens: Number of tokens used.
            token_type: 'input' or 'output'.
        """
        TOKEN_USAGE_TOTAL.labels(type=token_type).inc(tokens)

        if token_type == "input":
            self._snapshot.token_input += tokens
        else:
            self._snapshot.token_output += tokens

        logger.debug("metrics: token usage recorded", tokens=tokens, type=token_type)

    def record_tool_call(
        self,
        tool_name: str,
        success: bool = True,
    ) -> None:
        """Record a tool call.

        Args:
            tool_name: Name of the tool that was called.
            success: Whether the tool call succeeded.
        """
        status = "success" if success else "failure"
        TOOL_CALLS_TOTAL.labels(tool_name=tool_name, status=status).inc()

        if success:
            self._snapshot.tool_calls_success[tool_name] = \
                self._snapshot.tool_calls_success.get(tool_name, 0) + 1
        else:
            self._snapshot.tool_calls_failure[tool_name] = \
                self._snapshot.tool_calls_failure.get(tool_name, 0) + 1

        logger.debug("metrics: tool call recorded", tool=tool_name, success=success)

    def record_iteration(self) -> None:
        """Record an iteration in the agent loop."""
        ITERATIONS_TOTAL.inc()

    def get_metrics(self) -> str:
        """Get Prometheus metrics output.

        Returns:
            Prometheus text format metrics string.
        """
        return generate_latest(_registry).decode("utf-8")

    def get_snapshot(self) -> MetricSnapshot:
        """Get a snapshot of current metrics values.

        Note: This returns a copy of internal state, not live Prometheus data.
        For accurate Prometheus metrics, use get_metrics().

        Returns:
            MetricSnapshot with current values.
        """
        return MetricSnapshot(
            requests_total=self._snapshot.requests_total,
            requests_success=self._snapshot.requests_success,
            requests_failed=self._snapshot.requests_failed,
            active_requests=self._snapshot.active_requests,
            token_input=self._snapshot.token_input,
            token_output=self._snapshot.token_output,
            tool_calls_success=dict(self._snapshot.tool_calls_success),
            tool_calls_failure=dict(self._snapshot.tool_calls_failure),
            duration_samples=self._snapshot.duration_samples,
            duration_sum=self._snapshot.duration_sum,
        )

    def get_summary(self) -> Dict:
        """Get a human-readable summary of metrics.

        Returns:
            Dictionary with metric summaries.
        """
        snapshot = self.get_snapshot()
        avg_duration = (
            snapshot.duration_sum / snapshot.duration_samples
            if snapshot.duration_samples > 0
            else 0.0
        )

        return {
            "uptime_seconds": time.time() - self._start_time,
            "requests": {
                "total": snapshot.requests_total,
                "success": snapshot.requests_success,
                "failed": snapshot.requests_failed,
                "active": snapshot.active_requests,
                "success_rate": (
                    snapshot.requests_success / snapshot.requests_total * 100
                    if snapshot.requests_total > 0
                    else 0.0
                ),
            },
            "tokens": {
                "input": snapshot.token_input,
                "output": snapshot.token_output,
                "total": snapshot.token_input + snapshot.token_output,
            },
            "tools": {
                "success": snapshot.tool_calls_success,
                "failure": snapshot.tool_calls_failure,
                "total_success": sum(snapshot.tool_calls_success.values()),
                "total_failure": sum(snapshot.tool_calls_failure.values()),
            },
            "performance": {
                "avg_duration_seconds": round(avg_duration, 3),
                "total_duration_seconds": round(snapshot.duration_sum, 3),
            },
        }

    def check_alerts(self) -> List:
        """Check metrics against alert rules.

        Returns:
            List of triggered alerts.
        """
        from .alerts import check_alerts

        # Build metrics dict for alert checking
        summary = self.get_summary()

        # Add token usage ratio for alert checking
        from ..utils.token_manager import get_token_counter

        try:
            token_counter = get_token_counter(settings.default_model)
            token_budget = token_counter.get_token_budget()
            current_tokens = summary["tokens"]["total"]
            usage_ratio = current_tokens / token_budget if token_budget > 0 else 0
        except Exception:
            token_budget = 64000  # Default
            current_tokens = summary["tokens"]["total"]
            usage_ratio = current_tokens / token_budget if token_budget > 0 else 0

        # Build alert metrics dict
        alert_metrics = {
            "requests": summary["requests"],
            "tokens": summary["tokens"],
            "tools": summary["tools"],
            "performance": summary["performance"],
            "token_usage": {
                "current_tokens": current_tokens,
                "token_budget": token_budget,
                "usage_ratio": usage_ratio,
            },
        }

        return check_alerts(alert_metrics)

    @contextmanager
    def request_context(self, error_type: Optional[str] = None):
        """Context manager for request timing.

        Args:
            error_type: Error classification if the request fails.

        Yields:
            None

        Example:
            with collector.request_context() as ctx:
                # ... do work ...
                pass  # Success recorded on exit

            # Or with error handling:
            try:
                with collector.request_context() as ctx:
                    # ... do work that might fail ...
                    pass
            except Exception as e:
                # Failure already recorded by context manager
                pass
        """
        start = self.record_request_start()
        success = True

        try:
            yield
        except Exception as e:
            success = False
            # Record failure with error type
            duration = time.time() - start
            self.record_request_end(
                success=False,
                duration=duration,
                error_type=error_type or type(e).__name__,
            )
            raise
        finally:
            if success:
                duration = time.time() - start
                self.record_request_end(success=True, duration=duration)


# =============================================================================
# Global Instance
# =============================================================================

_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create the global metrics collector instance.

    This function provides backward compatibility with existing code.
    New code should prefer ApplicationContext.metrics_collector.

    Returns:
        Singleton MetricsCollector instance.
    """
    global _metrics_collector
    if _metrics_collector is None:
        # Try to use ApplicationContext first
        try:
            from mini_claude.context import get_context
            ctx = get_context()
            # Check if context has a cached instance
            if ctx._metrics_collector.is_initialized():
                _metrics_collector = ctx.metrics_collector
            else:
                _metrics_collector = MetricsCollector()
                # Sync back to context
                ctx.metrics_collector = _metrics_collector
        except ImportError:
            # Fallback to standalone creation
            _metrics_collector = MetricsCollector()
        logger.debug("metrics: collector initialized")
    return _metrics_collector


def reset_metrics_collector() -> None:
    """Reset the global metrics collector.

    Useful for testing.
    """
    global _metrics_collector
    _metrics_collector = None
    # Also reset in context
    try:
        from mini_claude.context import get_context
        ctx = get_context()
        ctx._metrics_collector.reset()
    except ImportError:
        pass


# =============================================================================
# Convenience Functions
# =============================================================================

def record_request_start() -> float:
    """Record request start using global collector."""
    return get_metrics_collector().record_request_start()


def record_request_end(
    success: bool,
    duration: float,
    error_type: Optional[str] = None,
) -> None:
    """Record request end using global collector."""
    get_metrics_collector().record_request_end(success, duration, error_type)


def record_token_usage(tokens: int, token_type: str = "input") -> None:
    """Record token usage using global collector."""
    get_metrics_collector().record_token_usage(tokens, token_type)


def record_tool_call(tool_name: str, success: bool = True) -> None:
    """Record tool call using global collector."""
    get_metrics_collector().record_tool_call(tool_name, success)


def get_metrics() -> str:
    """Get Prometheus metrics output using global collector."""
    return get_metrics_collector().get_metrics()


def get_metrics_summary() -> Dict:
    """Get metrics summary using global collector."""
    return get_metrics_collector().get_summary()


# =============================================================================
# Prometheus HTTP Server
# =============================================================================

async def start_metrics_server(port: int = 9090, host: str = "0.0.0.0") -> None:
    """Start Prometheus metrics HTTP server.

    This runs an HTTP server that exposes /metrics endpoint
    for Prometheus scraping.

    Args:
        port: Port to listen on (default: 9090).
        host: Host to bind to (default: 0.0.0.0).
    """
    from prometheus_client import start_http_server

    logger.info(f"Starting metrics server on {host}:{port}")

    # Run in a thread to not block async event loop
    import asyncio

    def run_server():
        start_http_server(port, host, registry=_registry)

    # Run in executor to not block
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_server)

    logger.info(f"Metrics server started on http://{host}:{port}/metrics")


def run_metrics_server_sync(port: int = 9090, host: str = "0.0.0.0") -> None:
    """Start Prometheus metrics HTTP server (synchronous version).

    Args:
        port: Port to listen on (default: 9090).
        host: Host to bind to (default: 0.0.0.0).
    """
    from prometheus_client import start_http_server

    logger.info(f"Starting metrics server on {host}:{port}")
    start_http_server(port, host, registry=_registry)
    logger.info(f"Metrics server started on http://{host}:{port}/metrics")

    # Keep running
    import signal
    import time

    def handle_signal(signum, frame):
        logger.info("Shutting down metrics server")
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down metrics server")
