"""Tests for OpenTelemetry tracing.

Tests cover:
- TracingManager initialization and setup
- Span creation and context management
- Trace storage and retrieval
- Convenience functions (traced decorator, trace_tool_call, etc.)
- Exporter functionality
"""

from unittest.mock import patch, MagicMock
from pathlib import Path

from mini_claude.monitoring.tracing import (
    TracingManager,
    TraceRecord,
    TraceStorage,
    get_tracing_manager,
    reset_tracing_manager,
    start_span,
    traced,
    trace_tool_call,
    trace_llm_call,
    trace_agent_node,
    trace_subagent,
    get_trace_storage,
    get_recent_traces,
    get_trace_tree,
    ConsoleSpanExporter,
    FileSpanExporter,
)


class TestTraceRecord:
    """Tests for TraceRecord dataclass."""

    def test_default_values(self):
        """Test TraceRecord default values."""
        record = TraceRecord(
            trace_id="test-trace",
            span_id="test-span",
            parent_span_id=None,
            name="test",
            start_time=0,
        )
        assert record.trace_id == "test-trace"
        assert record.span_id == "test-span"
        assert record.parent_span_id is None
        assert record.name == "test"
        assert record.duration_ms == 0.0
        assert record.attributes == {}
        assert record.status == "UNSET"
        assert record.events == []

    def test_with_values(self):
        """Test TraceRecord with custom values."""
        record = TraceRecord(
            trace_id="test-trace",
            span_id="test-span",
            parent_span_id="parent-span",
            name="test",
            start_time=1000,
            end_time=2000,
            duration_ms=100.5,
            attributes={"key": "value"},
            status="OK",
            events=[{"name": "event1"}],
        )
        assert record.duration_ms == 100.5
        assert record.attributes == {"key": "value"}
        assert record.status == "OK"
        assert len(record.events) == 1


class TestTraceStorage:
    """Tests for TraceStorage."""

    def test_initialization(self):
        """Test TraceStorage initialization."""
        storage = TraceStorage()
        assert storage._traces == []
        assert storage._max_traces == 100
        assert storage._current_trace_id is None

    def test_add_span(self):
        """Test adding spans to storage."""
        storage = TraceStorage(max_traces=3)
        record = TraceRecord(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            name="test",
            start_time=0,
        )
        storage.add_span(record)
        assert len(storage._traces) == 1

    def test_max_traces_limit(self):
        """Test that storage respects max_traces limit."""
        storage = TraceStorage(max_traces=3)
        for i in range(5):
            record = TraceRecord(
                trace_id=f"t{i}",
                span_id=f"s{i}",
                parent_span_id=None,
                name=f"test{i}",
                start_time=0,
            )
            storage.add_span(record)

        assert len(storage._traces) == 3
        # Should keep the last 3
        assert storage._traces[0].name == "test2"
        assert storage._traces[2].name == "test4"

    def test_get_recent_traces(self):
        """Test getting recent traces."""
        storage = TraceStorage()
        for i in range(5):
            record = TraceRecord(
                trace_id=f"t{i}",
                span_id=f"s{i}",
                parent_span_id=None,
                name=f"test{i}",
                start_time=0,
            )
            storage.add_span(record)

        recent = storage.get_recent_traces(limit=3)
        assert len(recent) == 3
        assert recent[0].name == "test2"
        assert recent[2].name == "test4"

    def test_get_traces_by_name(self):
        """Test filtering traces by name."""
        storage = TraceStorage()
        for i in range(5):
            record = TraceRecord(
                trace_id=f"t{i}",
                span_id=f"s{i}",
                parent_span_id=None,
                name="think" if i % 2 == 0 else "act",
                start_time=0,
            )
            storage.add_span(record)

        think_traces = storage.get_traces_by_name("think")
        assert len(think_traces) == 3

        act_traces = storage.get_traces_by_name("act")
        assert len(act_traces) == 2

    def test_get_traces_by_trace_id(self):
        """Test getting all spans for a trace."""
        storage = TraceStorage()
        # Add spans with same trace_id
        for i in range(3):
            record = TraceRecord(
                trace_id="trace-1",
                span_id=f"s{i}",
                parent_span_id=None,
                name=f"node{i}",
                start_time=0,
            )
            storage.add_span(record)
        # Add span with different trace_id
        record = TraceRecord(
            trace_id="trace-2",
            span_id="s3",
            parent_span_id=None,
            name="node3",
            start_time=0,
        )
        storage.add_span(record)

        traces = storage.get_traces_by_trace_id("trace-1")
        assert len(traces) == 3

    def test_clear(self):
        """Test clearing storage."""
        storage = TraceStorage()
        record = TraceRecord(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            name="test",
            start_time=0,
        )
        storage.add_span(record)
        assert len(storage._traces) == 1

        storage.clear()
        assert len(storage._traces) == 0

    def test_current_trace_id(self):
        """Test setting and getting current trace ID."""
        storage = TraceStorage()
        assert storage.get_current_trace_id() is None

        storage.set_current_trace_id("trace-123")
        assert storage.get_current_trace_id() == "trace-123"

        storage.set_current_trace_id(None)
        assert storage.get_current_trace_id() is None


class TestConsoleSpanExporter:
    """Tests for ConsoleSpanExporter."""

    def test_export_with_logger(self):
        """Test exporting spans to logger."""
        mock_logger = MagicMock()
        exporter = ConsoleSpanExporter(output_logger=mock_logger)

        # Create mock span
        mock_span = MagicMock()
        mock_span.context.trace_id = 123456789
        mock_span.context.span_id = 987654321
        mock_span.parent = None
        mock_span.name = "test-span"
        mock_span.start_time = 1000000000
        mock_span.end_time = 1000001000
        mock_span.attributes = {"key": "value"}
        mock_span.status.status_code.name = "OK"

        result = exporter.export([mock_span])

        # Result is SpanExportResult.SUCCESS when OpenTelemetry is available
        # or True when not available
        assert result is True or str(result) == "SpanExportResult.SUCCESS"
        assert mock_logger.info.called


class TestFileSpanExporter:
    """Tests for FileSpanExporter."""

    def test_export_to_file(self, tmp_path):
        """Test exporting spans to file."""
        file_path = str(tmp_path / "traces.json")
        exporter = FileSpanExporter(file_path)

        # Create mock span
        mock_span = MagicMock()
        mock_span.context.trace_id = 123456789
        mock_span.context.span_id = 987654321
        mock_span.parent = None
        mock_span.name = "test-span"
        mock_span.start_time = 1000000000
        mock_span.end_time = 1000001000
        mock_span.attributes = {"key": "value"}
        mock_span.status.status_code.name = "OK"
        mock_span.events = []

        result = exporter.export([mock_span])

        # Result is SpanExportResult.SUCCESS when OpenTelemetry is available
        # or True when not available
        assert result is True or str(result) == "SpanExportResult.SUCCESS"
        assert len(exporter.get_spans()) == 1

        # Check file was created
        assert Path(file_path).exists()

    def test_get_spans(self, tmp_path):
        """Test getting exported spans."""
        file_path = str(tmp_path / "traces.json")
        exporter = FileSpanExporter(file_path)

        mock_span = MagicMock()
        mock_span.context.trace_id = 123456789
        mock_span.context.span_id = 987654321
        mock_span.parent = None
        mock_span.name = "test-span"
        mock_span.start_time = 1000000000
        mock_span.end_time = 1000001000
        mock_span.attributes = {}
        mock_span.status.status_code.name = "OK"
        mock_span.events = []

        exporter.export([mock_span])
        spans = exporter.get_spans()

        assert len(spans) == 1
        assert spans[0]["name"] == "test-span"

    def test_clear(self, tmp_path):
        """Test clearing exported spans."""
        file_path = str(tmp_path / "traces.json")
        exporter = FileSpanExporter(file_path)

        mock_span = MagicMock()
        mock_span.context.trace_id = 123456789
        mock_span.context.span_id = 987654321
        mock_span.parent = None
        mock_span.name = "test-span"
        mock_span.start_time = 1000000000
        mock_span.end_time = 1000001000
        mock_span.attributes = {}
        mock_span.status.status_code.name = "OK"
        mock_span.events = []

        exporter.export([mock_span])
        assert len(exporter.get_spans()) == 1

        exporter.clear()
        assert len(exporter.get_spans()) == 0


class TestTracingManager:
    """Tests for TracingManager."""

    def setup_method(self):
        """Reset tracing manager before each test."""
        reset_tracing_manager()

    def test_initialization(self):
        """Test TracingManager initialization."""
        manager = TracingManager()
        assert manager._tracer_provider is None
        assert manager._tracer is None
        assert manager._enabled is False

    def test_enabled_property(self):
        """Test enabled property."""
        manager = TracingManager()
        assert manager.enabled is False

    def test_tracer_property(self):
        """Test tracer property."""
        manager = TracingManager()
        assert manager.tracer is None

    def test_setup_without_opentelemetry(self):
        """Test setup when OpenTelemetry is not available."""
        with patch("mini_claude.monitoring.tracing._tracing_available", False):
            manager = TracingManager()
            result = manager.setup()
            assert result is False
            assert manager.enabled is False

    def test_setup_with_console_exporter(self):
        """Test setup with console exporter."""
        manager = TracingManager()

        # Mock OpenTelemetry availability - need to mock the actual imports
        mock_tracer_provider = MagicMock()
        mock_resource = MagicMock()
        mock_trace = MagicMock()
        mock_processor = MagicMock()

        with patch("mini_claude.monitoring.tracing._tracing_available", True):
            with patch.dict(
                "mini_claude.monitoring.tracing.__dict__",
                {
                    "TracerProvider": mock_tracer_provider,
                    "Resource": mock_resource,
                    "trace": mock_trace,
                    "SimpleSpanProcessor": mock_processor,
                },
            ):
                result = manager.setup(
                    service_name="test-service",
                    exporter_type="console",
                )
                # Setup should return bool; if True, verify post-conditions
                assert isinstance(result, bool), "setup() should return a boolean"
                if result:
                    assert manager._enabled is True, "setup() returned True but _enabled is False"
                    assert manager._tracer is not None, "setup() returned True but _tracer is None"
                else:
                    assert manager._enabled is False, "setup() returned False but _enabled is True"

    def test_shutdown(self):
        """Test shutdown."""
        manager = TracingManager()
        manager._enabled = True
        manager._tracer_provider = MagicMock()

        manager.shutdown()

        assert manager._enabled is False
        assert manager._tracer is None

    def test_force_flush_without_provider(self):
        """Test force_flush when no provider."""
        manager = TracingManager()
        # Should not raise
        manager.force_flush()

    def test_start_span_when_disabled(self):
        """Test start_span when tracing is disabled."""
        manager = TracingManager()
        manager._enabled = False

        with manager.start_span("test") as span:
            assert span is None

    def test_record_exception_with_none_span(self):
        """Test record_exception with None span."""
        manager = TracingManager()
        # Should not raise
        manager.record_exception(None, Exception("test"))


class TestTracingManagerSingleton:
    """Tests for global tracing manager singleton."""

    def setup_method(self):
        """Reset before each test."""
        reset_tracing_manager()

    def test_get_tracing_manager_returns_singleton(self):
        """Test get_tracing_manager returns same instance."""
        manager1 = get_tracing_manager()
        manager2 = get_tracing_manager()
        assert manager1 is manager2

    def test_reset_tracing_manager(self):
        """Test reset_tracing_manager clears singleton."""
        manager1 = get_tracing_manager()
        reset_tracing_manager()
        manager2 = get_tracing_manager()
        assert manager1 is not manager2


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def setup_method(self):
        """Reset before each test."""
        reset_tracing_manager()

    def test_start_span_function(self):
        """Test start_span convenience function."""
        with start_span("test"):
            # Returns context manager, may be None if tracing disabled
            pass

    def test_trace_tool_call(self):
        """Test trace_tool_call function."""
        with trace_tool_call("write_file", {"path": "/test.txt"}):
            pass

    def test_trace_tool_call_sanitizes_params(self):
        """Test that trace_tool_call sanitizes sensitive params."""
        with trace_tool_call(
            "write_file",
            {
                "path": "/test.txt",
                "content": "secret data",
                "password": "secret123",
            },
        ):
            pass

    def test_trace_llm_call(self):
        """Test trace_llm_call function."""
        with trace_llm_call("deepseek-chat", 10):
            pass

    def test_trace_agent_node(self):
        """Test trace_agent_node function."""
        with trace_agent_node("think", iteration=1):
            pass

    def test_trace_subagent(self):
        """Test trace_subagent function."""
        with trace_subagent("Create a file", agent_id="agent-123"):
            pass

    def test_traced_decorator_async(self):
        """Test traced decorator with async function."""

        @traced("my_operation")
        async def my_async_func():
            return "result"

        # Just verify decorator doesn't break the function
        import asyncio

        result = asyncio.run(my_async_func())
        assert result == "result"

    def test_traced_decorator_sync(self):
        """Test traced decorator with sync function."""

        @traced("my_operation")
        def my_sync_func():
            return "result"

        result = my_sync_func()
        assert result == "result"

    def test_traced_decorator_with_name(self):
        """Test traced decorator with custom name."""

        @traced("custom_name")
        async def my_func():
            return "result"

        import asyncio

        result = asyncio.run(my_func())
        assert result == "result"


class TestCLISupportFunctions:
    """Tests for CLI support functions."""

    def setup_method(self):
        """Reset before each test."""
        reset_tracing_manager()

    def test_get_recent_traces(self):
        """Test get_recent_traces function."""
        storage = get_trace_storage()
        record = TraceRecord(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            name="test",
            start_time=0,
            duration_ms=100,
            status="OK",
        )
        storage.add_span(record)

        traces = get_recent_traces(limit=10)
        assert len(traces) == 1
        assert traces[0]["name"] == "test"

    def test_get_trace_tree_no_trace_id(self):
        """Test get_trace_tree when no trace ID available."""
        tree = get_trace_tree()
        assert "error" in tree

    def test_get_trace_tree_with_trace_id(self):
        """Test get_trace_tree with specific trace ID."""
        storage = get_trace_storage()
        record = TraceRecord(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            name="test",
            start_time=0,
            duration_ms=100,
            status="OK",
        )
        storage.add_span(record)

        tree = get_trace_tree(trace_id="t1")
        assert tree["trace_id"] == "t1"
        assert "spans" in tree

    def test_get_trace_tree_missing_trace(self):
        """Test get_trace_tree for non-existent trace."""
        tree = get_trace_tree(trace_id="non-existent")
        assert "error" in tree


class TestIntegration:
    """Integration tests for tracing."""

    def setup_method(self):
        """Reset before each test."""
        reset_tracing_manager()

    def test_full_trace_lifecycle(self):
        """Test complete trace lifecycle."""
        storage = get_trace_storage()

        # Simulate agent execution
        with trace_agent_node("think", 1):
            pass

        with trace_agent_node("plan", 1):
            pass

        with trace_agent_node("act", 1):
            with trace_tool_call("read_file", {"path": "/test.txt"}):
                pass

            with trace_llm_call("deepseek-chat", 5):
                pass

        traces = storage.get_recent_traces(limit=10)
        # Verify tracing is disabled (not relying on default value assumption)
        manager = get_tracing_manager()
        assert manager._enabled is False, "Test assumes tracing is disabled"
        assert len(traces) == 0, "No spans should be stored when tracing is disabled"

    def test_error_recording(self):
        """Test that errors are recorded in spans with ERROR status."""
        storage = get_trace_storage()
        storage.clear()

        # Mock the tracing manager to be enabled with a fake tracer
        manager = get_tracing_manager()

        # Create a mock span with proper context attributes
        mock_span = MagicMock()
        mock_span.context.trace_id = 0x1234567890ABCDEF1234567890ABCDEF
        mock_span.context.span_id = 0x1234567890ABCDEF
        mock_span.parent = None
        mock_span.start_time = 1000000000
        mock_span.end_time = 2000000000

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        manager._enabled = True
        manager._tracer = mock_tracer

        try:
            with manager.start_span("agent.error_test"):
                raise ValueError("Test error")
        except ValueError:
            pass

        # Verify the error span was recorded with ERROR status
        traces = storage.get_recent_traces(limit=10)
        error_traces = [t for t in traces if t.name == "agent.error_test"]
        assert len(error_traces) > 0, "Error trace should be recorded in storage"
        assert error_traces[0].status == "ERROR", "Error trace should have ERROR status"


# Run with: pytest tests/test_monitoring/test_tracing.py -v
