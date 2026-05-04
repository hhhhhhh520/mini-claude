"""OpenTelemetry tracing for Mini Claude Code.

Provides distributed tracing for:
- Agent execution flow (think -> plan -> act -> observe -> reflect)
- Tool calls (tool_name, params, duration, result)
- LLM calls (model, prompt_tokens, completion_tokens)
- Sub-agent creation and execution

Usage:
    from mini_claude.monitoring.tracing import get_tracing_manager, traced

    # Initialize tracing
    manager = get_tracing_manager()
    manager.setup()

    # Use decorator
    @traced("operation_name")
    async def my_function():
        pass

    # Or use context manager
    with manager.start_span("operation_name") as span:
        span.set_attribute("key", "value")
"""

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from functools import wraps

from mini_claude.config.settings import settings
from mini_claude.utils.logger import get_logger

logger = get_logger("mini_claude.monitoring.tracing")

# OpenTelemetry imports (optional - graceful fallback)
_tracing_available = False
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.trace import Status, StatusCode, Span  # noqa: F401
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator  # noqa: F401
    from opentelemetry.context import Context  # noqa: F401

    # Exporter imports
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult  # noqa: F401

    # Try to import OTLP exporter
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # noqa: F401
        _otlp_available = True
    except ImportError:
        _otlp_available = False

    _tracing_available = True
except ImportError:
    _tracing_available = False
    logger.warning("OpenTelemetry not installed. Tracing disabled. Install with: pip install opentelemetry-api opentelemetry-sdk")


# =============================================================================
# Custom Exporters
# =============================================================================

class ConsoleSpanExporter:
    """Console exporter for debugging - prints spans to stdout."""

    def __init__(self, output_logger: Optional[Any] = None):
        """Initialize console exporter.

        Args:
            output_logger: Optional logger to use instead of print
        """
        self._logger = output_logger or logger

    def export(self, spans: List[Any]) -> Any:
        """Export spans to console.

        Args:
            spans: List of spans to export

        Returns:
            SpanExportResult.SUCCESS
        """
        for span in spans:
            span_dict = {
                "trace_id": format(span.context.trace_id, '032x'),
                "span_id": format(span.context.span_id, '016x'),
                "parent_span_id": format(span.parent.span_id, '016x') if span.parent else None,
                "name": span.name,
                "start_time": span.start_time,
                "end_time": span.end_time,
                "duration_ms": (span.end_time - span.start_time) // 1_000_000 if span.end_time else 0,
                "attributes": dict(span.attributes) if span.attributes else {},
                "status": span.status.status_code.name if hasattr(span, 'status') else "UNSET",
            }
            self._logger.info(f"[TRACE] {json.dumps(span_dict, default=str)}")

        if _tracing_available:
            from opentelemetry.sdk.trace.export import SpanExportResult
            return SpanExportResult.SUCCESS
        return True


class FileSpanExporter:
    """File exporter - writes spans to a JSON file."""

    def __init__(self, file_path: str):
        """Initialize file exporter.

        Args:
            file_path: Path to the trace file
        """
        self._file_path = Path(file_path)
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._spans: List[Dict] = []

    def export(self, spans: List[Any]) -> Any:
        """Export spans to file.

        Args:
            spans: List of spans to export

        Returns:
            SpanExportResult.SUCCESS
        """
        for span in spans:
            span_dict = {
                "trace_id": format(span.context.trace_id, '032x'),
                "span_id": format(span.context.span_id, '016x'),
                "parent_span_id": format(span.parent.span_id, '016x') if span.parent else None,
                "name": span.name,
                "start_time": span.start_time,
                "end_time": span.end_time,
                "duration_ms": (span.end_time - span.start_time) // 1_000_000 if span.end_time else 0,
                "attributes": dict(span.attributes) if span.attributes else {},
                "status": span.status.status_code.name if hasattr(span, 'status') else "UNSET",
                "events": [
                    {
                        "name": event.name,
                        "timestamp": event.timestamp,
                        "attributes": dict(event.attributes) if event.attributes else {},
                    }
                    for event in (span.events or [])
                ],
            }
            self._spans.append(span_dict)

        # Write to file
        self._write_spans()

        if _tracing_available:
            from opentelemetry.sdk.trace.export import SpanExportResult
            return SpanExportResult.SUCCESS
        return True

    def _write_spans(self):
        """Write spans to file."""
        with open(self._file_path, 'w', encoding='utf-8') as f:
            json.dump({
                "spans": self._spans,
                "exported_at": datetime.now().isoformat(),
            }, f, indent=2, default=str)

    def get_spans(self) -> List[Dict]:
        """Get all exported spans."""
        return self._spans.copy()

    def clear(self):
        """Clear all stored spans."""
        self._spans = []
        self._write_spans()


# =============================================================================
# Trace Storage (for CLI access)
# =============================================================================

@dataclass
class TraceRecord:
    """A record of a traced operation."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    start_time: int
    end_time: Optional[int] = None
    duration_ms: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: str = "UNSET"
    events: List[Dict[str, Any]] = field(default_factory=list)


class TraceStorage:
    """In-memory storage for recent traces."""

    def __init__(self, max_traces: int = 100):
        """Initialize trace storage.

        Args:
            max_traces: Maximum number of traces to store
        """
        self._traces: List[TraceRecord] = []
        self._max_traces = max_traces
        self._current_trace_id: Optional[str] = None

    def add_span(self, span: TraceRecord):
        """Add a span to storage."""
        self._traces.append(span)
        if len(self._traces) > self._max_traces:
            self._traces = self._traces[-self._max_traces:]

    def get_recent_traces(self, limit: int = 10) -> List[TraceRecord]:
        """Get recent traces."""
        return self._traces[-limit:]

    def get_traces_by_name(self, name: str) -> List[TraceRecord]:
        """Get traces by operation name."""
        return [t for t in self._traces if t.name == name]

    def get_traces_by_trace_id(self, trace_id: str) -> List[TraceRecord]:
        """Get all spans for a trace."""
        return [t for t in self._traces if t.trace_id == trace_id]

    def clear(self):
        """Clear all stored traces."""
        self._traces = []

    def set_current_trace_id(self, trace_id: Optional[str]):
        """Set the current trace ID."""
        self._current_trace_id = trace_id

    def get_current_trace_id(self) -> Optional[str]:
        """Get the current trace ID."""
        return self._current_trace_id


# Global trace storage
_trace_storage = TraceStorage()


def get_trace_storage() -> TraceStorage:
    """Get the global trace storage."""
    return _trace_storage


# =============================================================================
# Tracing Manager
# =============================================================================

class TracingManager:
    """Manages OpenTelemetry tracing configuration and lifecycle.

    Supports multiple exporters:
    - console: Print traces to console (debugging)
    - otlp: Send to OTLP endpoint (Jaeger/Zipkin)
    - file: Write to JSON file

    Example:
        manager = TracingManager()
        manager.setup(service_name="my-service", exporter_type="console")

        # Get tracer
        tracer = manager.get_tracer()

        # Create span
        with tracer.start_as_current_span("my_operation") as span:
            span.set_attribute("key", "value")

        # Shutdown
        manager.shutdown()
    """

    def __init__(self):
        """Initialize tracing manager."""
        self._tracer_provider: Optional[Any] = None
        self._tracer: Optional[Any] = None
        self._exporter: Optional[Any] = None
        self._enabled: bool = False
        self._service_name: str = "mini-claude"
        self._exporter_type: str = "console"

    @property
    def enabled(self) -> bool:
        """Check if tracing is enabled."""
        return self._enabled

    @property
    def tracer(self) -> Optional[Any]:
        """Get the tracer instance."""
        return self._tracer

    def setup(
        self,
        service_name: Optional[str] = None,
        exporter_type: Optional[str] = None,
        otlp_endpoint: Optional[str] = None,
        sample_rate: Optional[float] = None,
        file_path: Optional[str] = None,
    ) -> bool:
        """Initialize OpenTelemetry tracing.

        Args:
            service_name: Service name for traces
            exporter_type: Exporter type (console, otlp, file)
            otlp_endpoint: OTLP endpoint URL (for otlp exporter)
            sample_rate: Sampling rate (0.0 to 1.0)
            file_path: File path for file exporter

        Returns:
            True if setup successful, False otherwise
        """
        if not _tracing_available:
            logger.warning("Tracing not available - OpenTelemetry not installed")
            return False

        # Use settings defaults
        service_name = service_name or settings.tracing_service_name
        exporter_type = exporter_type or settings.tracing_exporter
        otlp_endpoint = otlp_endpoint or settings.tracing_otlp_endpoint
        sample_rate = sample_rate if sample_rate is not None else settings.tracing_sample_rate
        file_path = file_path or settings.tracing_file_path

        self._service_name = service_name
        self._exporter_type = exporter_type

        try:
            # Create resource
            resource = Resource.create({
                "service.name": service_name,
                "service.version": "1.0.0",
            })

            # Create tracer provider
            self._tracer_provider = TracerProvider(resource=resource)

            # Configure sampling
            # Note: For simplicity, we use always sampling if rate > 0
            # Production would use TraceIdRatioBased sampler

            # Create exporter based on type
            self._exporter = self._create_exporter(
                exporter_type=exporter_type,
                otlp_endpoint=otlp_endpoint,
                file_path=file_path,
            )

            if self._exporter is None:
                return False

            # Add span processor
            # Use SimpleSpanProcessor for console/file (immediate output)
            # Use BatchSpanProcessor for OTLP (better performance)
            if exporter_type == "otlp":
                processor = BatchSpanProcessor(self._exporter)
            else:
                processor = SimpleSpanProcessor(self._exporter)

            self._tracer_provider.add_span_processor(processor)

            # Set global tracer provider
            trace.set_tracer_provider(self._tracer_provider)

            # Create tracer
            self._tracer = trace.get_tracer(service_name, "1.0.0")

            self._enabled = True
            logger.info(
                "Tracing initialized",
                service_name=service_name,
                exporter_type=exporter_type,
                sample_rate=sample_rate,
            )
            return True

        except Exception as e:
            logger.error("Failed to initialize tracing", error=str(e))
            return False

    def _create_exporter(
        self,
        exporter_type: str,
        otlp_endpoint: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> Optional[Any]:
        """Create span exporter based on type.

        Args:
            exporter_type: Type of exporter (console, otlp, file)
            otlp_endpoint: OTLP endpoint URL
            file_path: File path for file exporter

        Returns:
            SpanExporter instance or None
        """
        if exporter_type == "console":
            return ConsoleSpanExporter()

        elif exporter_type == "file":
            return FileSpanExporter(file_path or "logs/traces.json")

        elif exporter_type == "otlp":
            if not _otlp_available:
                logger.warning("OTLP exporter not available. Install: pip install opentelemetry-exporter-otlp")
                return None

            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            return OTLPSpanExporter(endpoint=otlp_endpoint or "http://localhost:4317")

        else:
            logger.warning(f"Unknown exporter type: {exporter_type}, using console")
            return ConsoleSpanExporter()

    def get_tracer(self) -> Optional[Any]:
        """Get the tracer instance.

        Returns:
            Tracer instance or None if not initialized
        """
        return self._tracer

    @contextmanager
    def start_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """Start a new span as context manager.

        Args:
            name: Span name
            attributes: Optional span attributes

        Yields:
            Span instance or None if tracing disabled

        Example:
            with manager.start_span("my_operation", {"key": "value"}) as span:
                # Do work
                pass
        """
        if not self._enabled or self._tracer is None:
            yield None
            return

        with self._tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)

            # Store in trace storage
            trace_id = format(span.context.trace_id, '032x')
            span_id = format(span.context.span_id, '016x')
            parent_span_id = format(span.parent.span_id, '016x') if span.parent else None

            record = TraceRecord(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                name=name,
                start_time=span.start_time,
                attributes=attributes or {},
            )

            # Set current trace ID
            _trace_storage.set_current_trace_id(trace_id)

            try:
                yield span
                record.status = "OK"
            except Exception as e:
                record.status = "ERROR"
                self.record_exception(span, e)
                raise
            finally:
                record.end_time = span.end_time
                record.duration_ms = (span.end_time - span.start_time) // 1_000_000 if span.end_time else 0
                _trace_storage.add_span(record)

    def record_exception(self, span: Any, exception: Exception):
        """Record an exception on a span.

        Args:
            span: Span to record exception on
            exception: Exception to record
        """
        if span is None:
            return

        if _tracing_available:
            from opentelemetry.trace import Status, StatusCode
            span.set_status(Status(StatusCode.ERROR, str(exception)))
            span.record_exception(exception)

    def shutdown(self):
        """Shutdown tracing and flush remaining spans."""
        if self._tracer_provider:
            try:
                self._tracer_provider.shutdown()
                logger.info("Tracing shutdown complete")
            except Exception as e:
                logger.warning("Error during tracing shutdown", error=str(e))

        self._enabled = False
        self._tracer = None
        self._tracer_provider = None

    def force_flush(self, timeout_ms: int = 5000):
        """Force flush all pending spans.

        Args:
            timeout_ms: Timeout in milliseconds
        """
        if self._tracer_provider:
            try:
                self._tracer_provider.force_flush(timeout_millis=timeout_ms)
            except Exception as e:
                logger.warning("Error during trace flush", error=str(e))


# =============================================================================
# Global Instance
# =============================================================================

_tracing_manager: Optional[TracingManager] = None


def get_tracing_manager() -> TracingManager:
    """Get or create the global tracing manager instance.

    This function provides backward compatibility with existing code.
    New code should prefer ApplicationContext.tracing_manager.

    Returns:
        Singleton TracingManager instance.
    """
    global _tracing_manager
    if _tracing_manager is None:
        # Try to use ApplicationContext first
        try:
            from mini_claude.context import get_context
            ctx = get_context()
            if ctx._tracing_manager.is_initialized():
                _tracing_manager = ctx.tracing_manager
            else:
                _tracing_manager = TracingManager()
                # Auto-setup if enabled in settings
                if settings.tracing_enabled:
                    _tracing_manager.setup()
                ctx.tracing_manager = _tracing_manager
        except ImportError:
            _tracing_manager = TracingManager()
            # Auto-setup if enabled in settings
            if settings.tracing_enabled:
                _tracing_manager.setup()
    return _tracing_manager


def reset_tracing_manager():
    """Reset the global tracing manager.

    Useful for testing.
    """
    global _tracing_manager
    if _tracing_manager:
        _tracing_manager.shutdown()
    _tracing_manager = None
    _trace_storage.clear()
    # Also reset in context
    try:
        from mini_claude.context import get_context
        ctx = get_context()
        ctx._tracing_manager.reset()
    except ImportError:
        pass


# =============================================================================
# Convenience Functions
# =============================================================================

def start_span(name: str, attributes: Optional[Dict[str, Any]] = None):
    """Start a span using the global tracing manager.

    Args:
        name: Span name
        attributes: Optional span attributes

    Returns:
        Context manager yielding span
    """
    return get_tracing_manager().start_span(name, attributes)


def traced(
    name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
):
    """Decorator to trace a function.

    Args:
        name: Span name (defaults to function name)
        attributes: Static span attributes

    Returns:
        Decorated function

    Example:
        @traced("my_operation", {"key": "value"})
        async def my_function():
            pass
    """
    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            manager = get_tracing_manager()
            if not manager.enabled:
                return await func(*args, **kwargs)

            with manager.start_span(span_name, attributes):
                result = await func(*args, **kwargs)
                return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            manager = get_tracing_manager()
            if not manager.enabled:
                return func(*args, **kwargs)

            with manager.start_span(span_name, attributes):
                result = func(*args, **kwargs)
                return result

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def trace_tool_call(tool_name: str, params: Dict[str, Any]):
    """Create a span for tool execution.

    Args:
        tool_name: Name of the tool
        params: Tool parameters

    Returns:
        Context manager yielding span
    """
    # Sanitize params for tracing (remove sensitive data)
    safe_params = {
        k: v if k not in ("content", "api_key", "password", "token") else "[REDACTED]"
        for k, v in params.items()
    }

    return start_span(
        f"tool.{tool_name}",
        {
            "tool.name": tool_name,
            "tool.params": json.dumps(safe_params),
        },
    )


def trace_llm_call(model: str, messages_count: int):
    """Create a span for LLM call.

    Args:
        model: Model name
        messages_count: Number of messages

    Returns:
        Context manager yielding span
    """
    return start_span(
        f"llm.{model}",
        {
            "llm.model": model,
            "llm.messages_count": messages_count,
        },
    )


def trace_agent_node(node_name: str, iteration: int = 0):
    """Create a span for agent node execution.

    Args:
        node_name: Name of the node (think, plan, act, observe, reflect)
        iteration: Current iteration number

    Returns:
        Context manager yielding span
    """
    return start_span(
        f"agent.{node_name}",
        {
            "agent.node": node_name,
            "agent.iteration": iteration,
        },
    )


def trace_subagent(task: str, agent_id: Optional[str] = None):
    """Create a span for sub-agent execution.

    Args:
        task: Sub-agent task
        agent_id: Optional agent identifier

    Returns:
        Context manager yielding span
    """
    return start_span(
        "agent.subagent",
        {
            "agent.task": task[:200],  # Truncate long tasks
            "agent.id": agent_id or "unknown",
        },
    )


# =============================================================================
# CLI Support Functions
# =============================================================================

def get_recent_traces(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent traces for CLI display.

    Args:
        limit: Maximum number of traces to return

    Returns:
        List of trace records as dictionaries
    """
    storage = get_trace_storage()
    traces = storage.get_recent_traces(limit)

    return [
        {
            "trace_id": t.trace_id,
            "span_id": t.span_id,
            "parent_span_id": t.parent_span_id,
            "name": t.name,
            "duration_ms": t.duration_ms,
            "status": t.status,
            "attributes": t.attributes,
        }
        for t in traces
    ]


def get_trace_tree(trace_id: Optional[str] = None) -> Dict[str, Any]:
    """Get traces as a tree structure.

    Args:
        trace_id: Optional specific trace ID (uses current if not provided)

    Returns:
        Tree structure of traces
    """
    storage = get_trace_storage()

    if trace_id is None:
        trace_id = storage.get_current_trace_id()

    if trace_id is None:
        return {"error": "No trace ID available"}

    traces = storage.get_traces_by_trace_id(trace_id)

    if not traces:
        return {"error": f"No traces found for trace_id: {trace_id}"}

    # Build tree
    root_spans = [t for t in traces if t.parent_span_id is None]

    def build_tree(span: TraceRecord) -> Dict[str, Any]:
        children = [
            build_tree(s)
            for s in traces
            if s.parent_span_id == span.span_id
        ]
        return {
            "name": span.name,
            "duration_ms": span.duration_ms,
            "status": span.status,
            "attributes": span.attributes,
            "children": children,
        }

    return {
        "trace_id": trace_id,
        "spans": [build_tree(root) for root in root_spans],
    }
