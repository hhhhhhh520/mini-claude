"""Tests for Prometheus metrics collection.

Tests cover:
- MetricsCollector initialization and methods
- Metric recording functions
- Prometheus output format
- Context manager usage
"""

import pytest
import time

from mini_claude.monitoring.metrics import (
    MetricsCollector,
    MetricSnapshot,
    get_metrics_collector,
    reset_metrics_collector,
    record_request_start,
    record_request_end,
    record_token_usage,
    record_tool_call,
    get_metrics,
    get_metrics_summary,
)


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    def setup_method(self):
        """Reset metrics collector before each test."""
        reset_metrics_collector()

    def test_initialization(self):
        """Test MetricsCollector initialization."""
        collector = MetricsCollector()
        assert collector is not None
        assert collector._start_time > 0
        assert collector._snapshot is not None

    def test_singleton_pattern(self):
        """Test get_metrics_collector returns singleton."""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()
        assert collector1 is collector2

    def test_record_request_start(self):
        """Test recording request start."""
        collector = MetricsCollector()
        start_time = collector.record_request_start()
        assert start_time > 0
        assert collector._snapshot.active_requests == 1

    def test_record_request_end_success(self):
        """Test recording successful request end."""
        collector = MetricsCollector()
        collector.record_request_start()
        collector.record_request_end(success=True, duration=0.5)

        assert collector._snapshot.requests_total == 1
        assert collector._snapshot.requests_success == 1
        assert collector._snapshot.requests_failed == 0
        assert collector._snapshot.active_requests == 0

    def test_record_request_end_failure(self):
        """Test recording failed request end."""
        collector = MetricsCollector()
        collector.record_request_start()
        collector.record_request_end(success=False, duration=0.3, error_type="test_error")

        assert collector._snapshot.requests_total == 1
        assert collector._snapshot.requests_success == 0
        assert collector._snapshot.requests_failed == 1
        assert collector._snapshot.active_requests == 0

    def test_record_token_usage_input(self):
        """Test recording input token usage."""
        collector = MetricsCollector()
        collector.record_token_usage(100, "input")
        assert collector._snapshot.token_input == 100

    def test_record_token_usage_output(self):
        """Test recording output token usage."""
        collector = MetricsCollector()
        collector.record_token_usage(50, "output")
        assert collector._snapshot.token_output == 50

    def test_record_token_usage_default(self):
        """Test token usage defaults to input type."""
        collector = MetricsCollector()
        collector.record_token_usage(75)
        assert collector._snapshot.token_input == 75

    def test_record_tool_call_success(self):
        """Test recording successful tool call."""
        collector = MetricsCollector()
        collector.record_tool_call("write_file", success=True)

        assert collector._snapshot.tool_calls_success.get("write_file", 0) == 1
        assert collector._snapshot.tool_calls_failure.get("write_file", 0) == 0

    def test_record_tool_call_failure(self):
        """Test recording failed tool call."""
        collector = MetricsCollector()
        collector.record_tool_call("read_file", success=False)

        assert collector._snapshot.tool_calls_success.get("read_file", 0) == 0
        assert collector._snapshot.tool_calls_failure.get("read_file", 0) == 1

    def test_record_multiple_tool_calls(self):
        """Test recording multiple tool calls."""
        collector = MetricsCollector()
        collector.record_tool_call("write_file", success=True)
        collector.record_tool_call("write_file", success=True)
        collector.record_tool_call("write_file", success=False)
        collector.record_tool_call("read_file", success=True)

        assert collector._snapshot.tool_calls_success.get("write_file", 0) == 2
        assert collector._snapshot.tool_calls_failure.get("write_file", 0) == 1
        assert collector._snapshot.tool_calls_success.get("read_file", 0) == 1

    def test_get_metrics_returns_string(self):
        """Test get_metrics returns Prometheus format string."""
        collector = MetricsCollector()
        collector.record_request_start()
        collector.record_request_end(success=True, duration=0.5)

        metrics = collector.get_metrics()
        assert isinstance(metrics, str)
        assert "mini_claude_requests_total" in metrics

    def test_get_snapshot(self):
        """Test get_snapshot returns MetricSnapshot."""
        collector = MetricsCollector()
        collector.record_request_start()
        collector.record_request_end(success=True, duration=0.5)
        collector.record_token_usage(100, "input")
        collector.record_tool_call("write_file", success=True)

        snapshot = collector.get_snapshot()
        assert isinstance(snapshot, MetricSnapshot)
        assert snapshot.requests_total == 1
        assert snapshot.requests_success == 1
        assert snapshot.token_input == 100
        assert snapshot.tool_calls_success.get("write_file", 0) == 1

    def test_get_summary(self):
        """Test get_summary returns human-readable dict."""
        collector = MetricsCollector()
        collector.record_request_start()
        collector.record_request_end(success=True, duration=0.5)
        collector.record_token_usage(100, "input")
        collector.record_token_usage(50, "output")
        collector.record_tool_call("write_file", success=True)
        collector.record_tool_call("write_file", success=False)

        summary = collector.get_summary()
        assert isinstance(summary, dict)
        assert "requests" in summary
        assert "tokens" in summary
        assert "tools" in summary
        assert "performance" in summary
        assert "uptime_seconds" in summary

        assert summary["requests"]["total"] == 1
        assert summary["requests"]["success"] == 1
        assert summary["tokens"]["input"] == 100
        assert summary["tokens"]["output"] == 50
        assert summary["tokens"]["total"] == 150
        assert summary["tools"]["total_success"] == 1
        assert summary["tools"]["total_failure"] == 1

    def test_success_rate_calculation(self):
        """Test success rate calculation in summary."""
        collector = MetricsCollector()

        # No requests yet
        summary = collector.get_summary()
        assert summary["requests"]["success_rate"] == 0.0

        # Add some requests
        for _ in range(3):
            collector.record_request_start()
            collector.record_request_end(success=True, duration=0.1)
        for _ in range(2):
            collector.record_request_start()
            collector.record_request_end(success=False, duration=0.1)

        summary = collector.get_summary()
        assert summary["requests"]["total"] == 5
        assert summary["requests"]["success_rate"] == 60.0  # 3/5 * 100

    def test_avg_duration_calculation(self):
        """Test average duration calculation in summary."""
        collector = MetricsCollector()

        collector.record_request_start()
        collector.record_request_end(success=True, duration=1.0)
        collector.record_request_start()
        collector.record_request_end(success=True, duration=3.0)

        summary = collector.get_summary()
        assert summary["performance"]["avg_duration_seconds"] == 2.0  # (1+3)/2

    def test_request_context_success(self):
        """Test request context manager for successful request."""
        collector = MetricsCollector()

        with collector.request_context():
            time.sleep(0.1)  # Simulate work

        assert collector._snapshot.requests_total == 1
        assert collector._snapshot.requests_success == 1

    def test_request_context_failure(self):
        """Test request context manager for failed request."""
        collector = MetricsCollector()

        with pytest.raises(ValueError):
            with collector.request_context(error_type="value_error"):
                raise ValueError("test error")

        assert collector._snapshot.requests_total == 1
        assert collector._snapshot.requests_failed == 1

    def test_concurrent_requests(self):
        """Test tracking multiple concurrent requests."""
        collector = MetricsCollector()

        # Start 3 requests
        collector.record_request_start()
        collector.record_request_start()
        collector.record_request_start()

        assert collector._snapshot.active_requests == 3

        # End 2
        collector.record_request_end(success=True, duration=0.1)
        collector.record_request_end(success=True, duration=0.1)

        assert collector._snapshot.active_requests == 1
        assert collector._snapshot.requests_total == 2
        assert collector._snapshot.requests_success == 2

        # End last one
        collector.record_request_end(success=False, duration=0.1)

        assert collector._snapshot.active_requests == 0
        assert collector._snapshot.requests_total == 3


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def setup_method(self):
        """Reset metrics collector before each test."""
        reset_metrics_collector()

    def test_record_request_start_function(self):
        """Test record_request_start convenience function."""
        start = record_request_start()
        assert start > 0

    def test_record_request_end_function(self):
        """Test record_request_end convenience function."""
        record_request_start()
        record_request_end(success=True, duration=0.5)

        summary = get_metrics_summary()
        assert summary["requests"]["total"] == 1

    def test_record_token_usage_function(self):
        """Test record_token_usage convenience function."""
        record_token_usage(100, "input")
        record_token_usage(50, "output")

        summary = get_metrics_summary()
        assert summary["tokens"]["input"] == 100
        assert summary["tokens"]["output"] == 50

    def test_record_tool_call_function(self):
        """Test record_tool_call convenience function."""
        record_tool_call("write_file", success=True)
        record_tool_call("read_file", success=False)

        summary = get_metrics_summary()
        assert summary["tools"]["total_success"] == 1
        assert summary["tools"]["total_failure"] == 1

    def test_get_metrics_function(self):
        """Test get_metrics convenience function."""
        record_request_start()
        record_request_end(success=True, duration=0.5)

        metrics = get_metrics()
        assert "mini_claude_requests_total" in metrics


class TestPrometheusFormat:
    """Tests for Prometheus output format."""

    def setup_method(self):
        """Reset metrics collector before each test."""
        reset_metrics_collector()

    def test_metrics_output_format(self):
        """Test Prometheus text format output."""
        collector = MetricsCollector()
        collector.record_request_start()
        collector.record_request_end(success=True, duration=0.5)
        collector.record_token_usage(100, "input")
        collector.record_tool_call("write_file", success=True)

        output = collector.get_metrics()

        # Check for expected metric names
        assert "mini_claude_requests_total" in output
        assert "mini_claude_requests_success" in output
        assert "mini_claude_token_usage_total" in output
        assert "mini_claude_tool_calls_total" in output
        assert "mini_claude_request_duration_seconds" in output

    def test_labeled_metrics(self):
        """Test metrics with labels."""
        collector = MetricsCollector()
        collector.record_tool_call("write_file", success=True)
        collector.record_tool_call("write_file", success=False)
        collector.record_tool_call("read_file", success=True)

        output = collector.get_metrics()

        # Check for label format
        assert 'tool_name="write_file"' in output
        assert 'tool_name="read_file"' in output
        assert 'status="success"' in output
        assert 'status="failure"' in output


class TestMetricSnapshot:
    """Tests for MetricSnapshot dataclass."""

    def test_default_values(self):
        """Test MetricSnapshot default values."""
        snapshot = MetricSnapshot()
        assert snapshot.requests_total == 0
        assert snapshot.requests_success == 0
        assert snapshot.requests_failed == 0
        assert snapshot.active_requests == 0
        assert snapshot.token_input == 0
        assert snapshot.token_output == 0
        assert snapshot.tool_calls_success == {}
        assert snapshot.tool_calls_failure == {}
        assert snapshot.duration_samples == 0
        assert snapshot.duration_sum == 0.0


class TestIntegration:
    """Integration tests for metrics collection."""

    def setup_method(self):
        """Reset metrics collector before each test."""
        reset_metrics_collector()

    def test_full_request_lifecycle(self):
        """Test complete request lifecycle with metrics."""
        collector = MetricsCollector()

        # Start request
        start = collector.record_request_start()

        # Simulate LLM processing
        time.sleep(0.01)
        collector.record_token_usage(500, "input")

        # Simulate tool calls
        collector.record_tool_call("read_file", success=True)
        collector.record_token_usage(200, "output")

        collector.record_tool_call("write_file", success=True)
        collector.record_token_usage(100, "input")
        collector.record_token_usage(150, "output")

        # End request
        duration = time.time() - start
        collector.record_request_end(success=True, duration=duration)

        # Verify all metrics recorded
        summary = collector.get_summary()
        assert summary["requests"]["total"] == 1
        assert summary["requests"]["success"] == 1
        assert summary["tokens"]["input"] == 600
        assert summary["tokens"]["output"] == 350
        assert summary["tools"]["total_success"] == 2

    def test_error_handling_metrics(self):
        """Test metrics are correctly recorded on errors."""
        collector = MetricsCollector()

        # Simulate request with errors
        start = collector.record_request_start()
        collector.record_token_usage(100, "input")

        # Some tools succeed, some fail
        collector.record_tool_call("read_file", success=True)
        collector.record_tool_call("write_file", success=False)

        # Request fails
        duration = time.time() - start
        collector.record_request_end(
            success=False,
            duration=duration,
            error_type="tool_error",
        )

        summary = collector.get_summary()
        assert summary["requests"]["failed"] == 1
        assert summary["tools"]["total_success"] == 1
        assert summary["tools"]["total_failure"] == 1


# Run with: pytest tests/test_monitoring/test_metrics.py -v
