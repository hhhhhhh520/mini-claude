"""Unit tests for health check endpoint."""

import json
import time
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mini_claude.monitoring.health import (
    HealthChecker,
    HealthStatus,
    ServiceHealth,
    ModelHealth,
    ToolHealth,
    HealthReport,
    check_health,
    run_health_server,
)


@pytest.fixture
def mock_llm_provider():
    """Create mock LLM provider."""
    provider = MagicMock()
    provider.model = "deepseek-chat"
    provider.provider = MagicMock(value="deepseek")

    # Create a mock response that has choices attribute (like LiteLLM ModelResponse)
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="OK"))]
    provider.chat = AsyncMock(return_value=mock_response)
    return provider


@pytest.fixture
def mock_tool_registry():
    """Create mock tool registry."""
    registry = MagicMock()
    registry.list_tools.return_value = [
        "read_file",
        "write_file",
        "edit_file",
        "run_command",
        "web_search",
    ]
    return registry


@pytest.fixture
def clean_health_checker() -> Generator[None, None, None]:
    """Reset health checker state before and after tests."""
    yield


class TestHealthStatus:
    """Test health status enum."""

    def test_status_values(self):
        """Test health status values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.DEGRADED.value == "degraded"


class TestServiceHealth:
    """Test service health data class."""

    def test_healthy_service(self):
        """Test healthy service status."""
        health = ServiceHealth(
            status=HealthStatus.HEALTHY,
            uptime_seconds=3600.0,
            memory_usage_mb=100.0,
            version="1.0.0",
        )

        assert health.status == HealthStatus.HEALTHY
        assert health.uptime_seconds == 3600.0
        assert health.memory_usage_mb == 100.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        health = ServiceHealth(
            status=HealthStatus.HEALTHY,
            uptime_seconds=60.0,
            memory_usage_mb=50.0,
            version="1.0.0",
        )

        data = health.to_dict()

        assert data["status"] == "healthy"
        assert data["uptime_seconds"] == 60.0
        assert data["memory_usage_mb"] == 50.0
        assert data["version"] == "1.0.0"

    def test_uptime_format(self):
        """Test human readable uptime format."""
        health = ServiceHealth(
            status=HealthStatus.HEALTHY,
            uptime_seconds=3665.0,  # 1h 1m 5s
            memory_usage_mb=50.0,
        )

        data = health.to_dict()
        assert "1h 1m 5s" == data["uptime_human"]


class TestModelHealth:
    """Test model health data class."""

    def test_healthy_model(self):
        """Test healthy model status."""
        health = ModelHealth(
            status=HealthStatus.HEALTHY,
            model_name="deepseek-chat",
            provider="deepseek",
            response_time_ms=150.0,
            last_check_time=time.time(),
        )

        assert health.status == HealthStatus.HEALTHY
        assert health.model_name == "deepseek-chat"

    def test_unhealthy_model_with_error(self):
        """Test unhealthy model with error message."""
        health = ModelHealth(
            status=HealthStatus.UNHEALTHY,
            model_name="claude-3",
            provider="anthropic",
            error_message="API key not configured",
            last_check_time=time.time(),
        )

        assert health.status == HealthStatus.UNHEALTHY
        assert health.error_message == "API key not configured"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        health = ModelHealth(
            status=HealthStatus.HEALTHY,
            model_name="deepseek-chat",
            provider="deepseek",
            response_time_ms=100.0,
            last_check_time=time.time(),
        )

        data = health.to_dict()

        assert data["status"] == "healthy"
        assert data["model_name"] == "deepseek-chat"
        assert data["provider"] == "deepseek"
        assert data["response_time_ms"] == 100.0


class TestToolHealth:
    """Test tool health data class."""

    def test_healthy_tools(self):
        """Test healthy tools status."""
        health = ToolHealth(
            status=HealthStatus.HEALTHY,
            total_tools=5,
            available_tools=5,
            tool_names=["read_file", "write_file", "edit_file"],
        )

        assert health.status == HealthStatus.HEALTHY
        assert health.total_tools == 5
        assert health.available_tools == 5

    def test_degraded_tools(self):
        """Test degraded tools status when some unavailable."""
        health = ToolHealth(
            status=HealthStatus.DEGRADED,
            total_tools=10,
            available_tools=8,
            unavailable_tools=["web_search", "weather"],
        )

        assert health.status == HealthStatus.DEGRADED
        assert len(health.unavailable_tools) == 2

    def test_to_dict(self):
        """Test conversion to dictionary."""
        health = ToolHealth(
            status=HealthStatus.HEALTHY,
            total_tools=5,
            available_tools=5,
            tool_names=["read_file", "write_file"],
        )

        data = health.to_dict()

        assert data["status"] == "healthy"
        assert data["total_tools"] == 5
        assert data["available_tools"] == 5


class TestHealthReport:
    """Test health report data class."""

    def test_full_report(self):
        """Test full health report."""
        service = ServiceHealth(
            status=HealthStatus.HEALTHY,
            uptime_seconds=3600.0,
            memory_usage_mb=100.0,
            version="1.0.0",
        )
        model = ModelHealth(
            status=HealthStatus.HEALTHY,
            model_name="deepseek-chat",
            provider="deepseek",
            response_time_ms=150.0,
            last_check_time=time.time(),
        )
        tools = ToolHealth(
            status=HealthStatus.HEALTHY,
            total_tools=5,
            available_tools=5,
            tool_names=["read_file", "write_file"],
        )

        report = HealthReport(
            service=service,
            model=model,
            tools=tools,
            timestamp=time.time(),
        )

        assert report.service.status == HealthStatus.HEALTHY
        assert report.model.status == HealthStatus.HEALTHY
        assert report.tools.status == HealthStatus.HEALTHY

    def test_overall_status_healthy(self):
        """Test overall status when all healthy."""
        service = ServiceHealth(
            status=HealthStatus.HEALTHY,
            uptime_seconds=60.0,
            memory_usage_mb=50.0,
        )
        model = ModelHealth(
            status=HealthStatus.HEALTHY,
            model_name="test",
            provider="test",
            last_check_time=time.time(),
        )
        tools = ToolHealth(status=HealthStatus.HEALTHY, total_tools=5, available_tools=5)

        report = HealthReport(
            service=service,
            model=model,
            tools=tools,
            timestamp=time.time(),
        )

        assert report.overall_status() == HealthStatus.HEALTHY

    def test_overall_status_unhealthy(self):
        """Test overall status when model unhealthy."""
        service = ServiceHealth(
            status=HealthStatus.HEALTHY,
            uptime_seconds=60.0,
            memory_usage_mb=50.0,
        )
        model = ModelHealth(
            status=HealthStatus.UNHEALTHY,
            model_name="test",
            provider="test",
            error_message="Connection failed",
            last_check_time=time.time(),
        )
        tools = ToolHealth(status=HealthStatus.HEALTHY, total_tools=5, available_tools=5)

        report = HealthReport(
            service=service,
            model=model,
            tools=tools,
            timestamp=time.time(),
        )

        assert report.overall_status() == HealthStatus.UNHEALTHY

    def test_overall_status_degraded(self):
        """Test overall status when tools degraded."""
        service = ServiceHealth(
            status=HealthStatus.HEALTHY,
            uptime_seconds=60.0,
            memory_usage_mb=50.0,
        )
        model = ModelHealth(
            status=HealthStatus.HEALTHY,
            model_name="test",
            provider="test",
            last_check_time=time.time(),
        )
        tools = ToolHealth(
            status=HealthStatus.DEGRADED,
            total_tools=10,
            available_tools=8,
            unavailable_tools=["web_search"],
        )

        report = HealthReport(
            service=service,
            model=model,
            tools=tools,
            timestamp=time.time(),
        )

        assert report.overall_status() == HealthStatus.DEGRADED

    def test_to_dict(self):
        """Test conversion to dictionary."""
        service = ServiceHealth(
            status=HealthStatus.HEALTHY,
            uptime_seconds=3600.0,
            memory_usage_mb=100.0,
            version="1.0.0",
        )
        model = ModelHealth(
            status=HealthStatus.HEALTHY,
            model_name="deepseek-chat",
            provider="deepseek",
            response_time_ms=100.0,
            last_check_time=time.time(),
        )
        tools = ToolHealth(
            status=HealthStatus.HEALTHY,
            total_tools=5,
            available_tools=5,
            tool_names=["read_file"],
        )

        report = HealthReport(
            service=service,
            model=model,
            tools=tools,
            timestamp=time.time(),
        )

        data = report.to_dict()

        assert "service" in data
        assert "model" in data
        assert "tools" in data
        assert "timestamp" in data
        assert "overall_status" in data


class TestHealthChecker:
    """Test health checker class."""

    def test_init_with_defaults(self):
        """Test initialization with default settings."""
        checker = HealthChecker()

        assert checker.start_time is not None
        assert checker.version == "1.0.0"

    def test_init_with_custom_settings(self):
        """Test initialization with custom settings."""
        checker = HealthChecker(
            version="2.0.0",
            model_name="claude-3",
        )

        assert checker.version == "2.0.0"
        assert checker.model_name == "claude-3"

    def test_get_uptime(self):
        """Test uptime calculation."""
        checker = HealthChecker()
        time.sleep(0.1)  # Small delay

        uptime = checker.get_uptime()

        assert uptime >= 0.1
        assert uptime < 1.0  # Should be less than 1 second

    def test_get_memory_usage(self):
        """Test memory usage retrieval."""
        checker = HealthChecker()

        usage = checker.get_memory_usage()

        # Should return positive value
        assert usage > 0

    def test_check_service_health(self):
        """Test service health check."""
        checker = HealthChecker()

        health = checker.check_service_health()

        assert health.status == HealthStatus.HEALTHY
        assert health.uptime_seconds >= 0
        assert health.memory_usage_mb > 0
        assert health.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_check_model_health_success(self, mock_llm_provider):
        """Test model health check with successful connection."""
        checker = HealthChecker()

        # Mock the LLMProvider import inside the method
        with patch("mini_claude.llm.provider.LLMProvider", return_value=mock_llm_provider):
            health = await checker.check_model_health()

        assert health.status == HealthStatus.HEALTHY
        assert health.response_time_ms >= 0  # Can be 0 for mocked responses

    @pytest.mark.asyncio
    async def test_check_model_health_failure(self):
        """Test model health check with connection failure."""
        checker = HealthChecker()

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(side_effect=Exception("Connection refused"))

        with patch("mini_claude.llm.provider.LLMProvider", return_value=mock_provider):
            health = await checker.check_model_health()

        assert health.status == HealthStatus.UNHEALTHY
        assert health.error_message is not None
        assert "Connection refused" in health.error_message

    def test_check_tools_health(self, mock_tool_registry):
        """Test tools health check."""
        checker = HealthChecker()

        with patch("mini_claude.monitoring.health.tool_registry", mock_tool_registry):
            health = checker.check_tools_health()

        assert health.status == HealthStatus.HEALTHY
        assert health.total_tools == 5
        assert health.available_tools == 5

    def test_check_tools_health_empty_registry(self):
        """Test tools health check with empty registry."""
        checker = HealthChecker()

        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = []

        with patch("mini_claude.monitoring.health.tool_registry", mock_registry):
            health = checker.check_tools_health()

        # Empty registry should still be healthy
        assert health.status == HealthStatus.HEALTHY
        assert health.total_tools == 0
        assert health.available_tools == 0

    @pytest.mark.asyncio
    async def test_check_health_full(self, mock_llm_provider, mock_tool_registry):
        """Test full health check."""
        checker = HealthChecker()

        with patch("mini_claude.llm.provider.LLMProvider", return_value=mock_llm_provider):
            with patch("mini_claude.monitoring.health.tool_registry", mock_tool_registry):
                report = await checker.check_health()

        assert report.service.status == HealthStatus.HEALTHY
        assert report.model.status == HealthStatus.HEALTHY
        assert report.tools.status == HealthStatus.HEALTHY
        assert report.overall_status() == HealthStatus.HEALTHY


class TestCheckHealthFunction:
    """Test convenience check_health function."""

    @pytest.mark.asyncio
    async def test_check_health_returns_report(self, mock_llm_provider, mock_tool_registry):
        """Test that check_health returns a health report."""
        # Reset the global checker
        from mini_claude.monitoring import health

        health._health_checker = None

        with patch("mini_claude.llm.provider.LLMProvider", return_value=mock_llm_provider):
            with patch("mini_claude.monitoring.health.tool_registry", mock_tool_registry):
                report = await check_health()

        assert report is not None
        assert isinstance(report, HealthReport)


class TestHealthServer:
    """Test health HTTP server."""

    @pytest.mark.asyncio
    async def test_run_health_server_creates_app(self):
        """Test that health server creates an aiohttp app."""
        app = await run_health_server(port=8080, run=False)

        # Check routes are registered
        # aiohttp uses route.resource to get path info
        registered_paths = []
        for route in app.router.routes():
            resource = route.resource
            if resource:
                # Get the canonical path from resource
                registered_paths.append(resource.canonical)

        assert "/health" in registered_paths
        assert "/healthz" in registered_paths
        assert "/ready" in registered_paths
        assert "/readyz" in registered_paths
        assert "/live" in registered_paths
        assert "/livez" in registered_paths


class TestHealthJSONOutput:
    """Test JSON output format."""

    def test_health_report_json_serialization(self):
        """Test that health report can be serialized to JSON."""
        service = ServiceHealth(
            status=HealthStatus.HEALTHY,
            uptime_seconds=3600.0,
            memory_usage_mb=100.0,
            version="1.0.0",
        )
        model = ModelHealth(
            status=HealthStatus.HEALTHY,
            model_name="deepseek-chat",
            provider="deepseek",
            response_time_ms=100.0,
            last_check_time=time.time(),
        )
        tools = ToolHealth(
            status=HealthStatus.HEALTHY,
            total_tools=5,
            available_tools=5,
            tool_names=["read_file", "write_file"],
        )

        report = HealthReport(
            service=service,
            model=model,
            tools=tools,
            timestamp=time.time(),
        )

        # Should be JSON serializable
        json_str = json.dumps(report.to_dict())
        data = json.loads(json_str)

        assert data["overall_status"] == "healthy"
        assert data["service"]["status"] == "healthy"
        assert data["model"]["model_name"] == "deepseek-chat"
        assert data["tools"]["total_tools"] == 5

    def test_health_report_to_json_method(self):
        """Test the to_json method."""
        service = ServiceHealth(
            status=HealthStatus.HEALTHY,
            uptime_seconds=3600.0,
            memory_usage_mb=100.0,
        )
        model = ModelHealth(
            status=HealthStatus.HEALTHY,
            model_name="test",
            provider="test",
            last_check_time=time.time(),
        )
        tools = ToolHealth(
            status=HealthStatus.HEALTHY,
            total_tools=5,
            available_tools=5,
        )

        report = HealthReport(
            service=service,
            model=model,
            tools=tools,
            timestamp=time.time(),
        )

        json_str = report.to_json()
        data = json.loads(json_str)

        assert data["overall_status"] == "healthy"
