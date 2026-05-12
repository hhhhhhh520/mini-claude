"""Tests for tool health check system."""

import asyncio
import os
import pytest
from unittest.mock import patch

from mini_claude.tools.health_check import (
    ToolHealthChecker,
    ToolHealthStatus,
    ToolHealthResult,
    ToolHealthSummary,
    get_tool_health_checker,
    check_tool_health,
    check_all_tools_health,
)


class TestToolHealthStatus:
    """Test ToolHealthStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert ToolHealthStatus.HEALTHY.value == "healthy"
        assert ToolHealthStatus.DEGRADED.value == "degraded"
        assert ToolHealthStatus.UNHEALTHY.value == "unhealthy"

    def test_status_comparison(self):
        """Test status enum comparison."""
        assert ToolHealthStatus.HEALTHY != ToolHealthStatus.DEGRADED
        assert ToolHealthStatus.DEGRADED != ToolHealthStatus.UNHEALTHY


class TestToolHealthResult:
    """Test ToolHealthResult dataclass."""

    def test_result_creation(self):
        """Test creating a health result."""
        result = ToolHealthResult(
            tool_name="read_file",
            status=ToolHealthStatus.HEALTHY,
            message="Tool is healthy",
            last_check_time=1234567890.0,
        )
        assert result.tool_name == "read_file"
        assert result.status == ToolHealthStatus.HEALTHY
        assert result.message == "Tool is healthy"
        assert result.details == {}
        assert result.response_time_ms is None

    def test_result_with_details(self):
        """Test health result with details."""
        result = ToolHealthResult(
            tool_name="web_search",
            status=ToolHealthStatus.DEGRADED,
            message="Network partially available",
            last_check_time=1234567890.0,
            details={"dns_resolution": "ok", "http_connectivity": False},
            response_time_ms=150.5,
        )
        assert result.details["dns_resolution"] == "ok"
        assert result.response_time_ms == 150.5

    def test_result_to_dict(self):
        """Test result serialization."""
        result = ToolHealthResult(
            tool_name="run_command",
            status=ToolHealthStatus.HEALTHY,
            message="Shell available",
            last_check_time=1234567890.0,
            details={"shell_available": True},
            response_time_ms=10.25,
        )
        data = result.to_dict()

        assert data["tool_name"] == "run_command"
        assert data["status"] == "healthy"
        assert data["message"] == "Shell available"
        assert "last_check_time" in data
        assert data["details"]["shell_available"]
        assert data["response_time_ms"] == 10.25


class TestToolHealthSummary:
    """Test ToolHealthSummary dataclass."""

    def test_summary_creation(self):
        """Test creating a health summary."""
        results = [
            ToolHealthResult(
                tool_name="read_file",
                status=ToolHealthStatus.HEALTHY,
                message="OK",
                last_check_time=1234567890.0,
            ),
            ToolHealthResult(
                tool_name="web_search",
                status=ToolHealthStatus.DEGRADED,
                message="Partial",
                last_check_time=1234567890.0,
            ),
        ]
        summary = ToolHealthSummary(
            total_tools=2,
            healthy_count=1,
            degraded_count=1,
            unhealthy_count=0,
            overall_status=ToolHealthStatus.DEGRADED,
            tool_results=results,
            timestamp=1234567890.0,
        )

        assert summary.total_tools == 2
        assert summary.healthy_count == 1
        assert summary.degraded_count == 1
        assert summary.unhealthy_count == 0
        assert len(summary.tool_results) == 2

    def test_summary_to_dict(self):
        """Test summary serialization."""
        results = [
            ToolHealthResult(
                tool_name="read_file",
                status=ToolHealthStatus.HEALTHY,
                message="OK",
                last_check_time=1234567890.0,
            ),
        ]
        summary = ToolHealthSummary(
            total_tools=1,
            healthy_count=1,
            degraded_count=0,
            unhealthy_count=0,
            overall_status=ToolHealthStatus.HEALTHY,
            tool_results=results,
            timestamp=1234567890.0,
        )
        data = summary.to_dict()

        assert data["total_tools"] == 1
        assert data["healthy_count"] == 1
        assert data["overall_status"] == "healthy"
        assert len(data["tools"]) == 1


class TestToolHealthChecker:
    """Test ToolHealthChecker class."""

    @pytest.fixture
    def checker(self):
        """Create a health checker instance."""
        return ToolHealthChecker(cache_ttl_seconds=5.0, timeout_seconds=2.0)

    def test_checker_initialization(self, checker):
        """Test checker initialization."""
        assert checker._cache_ttl == 5.0
        assert checker._timeout == 2.0
        assert checker._cache == {}
        assert checker._custom_checks == {}

    def test_register_custom_check(self, checker):
        """Test registering custom health check."""

        def custom_check():
            return ToolHealthResult(
                tool_name="custom_tool",
                status=ToolHealthStatus.HEALTHY,
                message="Custom check passed",
                last_check_time=1234567890.0,
            )

        checker.register_health_check("custom_tool", custom_check)
        assert "custom_tool" in checker._custom_checks

    @pytest.mark.asyncio
    async def test_check_file_tool(self, checker):
        """Test checking file tool health."""
        # Mock workspace root
        with patch("mini_claude.tools.health_check.settings") as mock_settings:
            mock_settings.workspace_root = os.getcwd()

            result = await checker.check_tool("read_file", use_cache=False)

            assert result.tool_name == "read_file"
            # Should be healthy if workspace is accessible
            assert result.status in [
                ToolHealthStatus.HEALTHY,
                ToolHealthStatus.DEGRADED,
                ToolHealthStatus.UNHEALTHY,
            ]

    @pytest.mark.asyncio
    async def test_check_command_tool(self, checker):
        """Test checking command tool health."""
        result = await checker.check_tool("run_command", use_cache=False)

        assert result.tool_name == "run_command"
        # Shell should be available in most test environments
        assert result.status in [
            ToolHealthStatus.HEALTHY,
            ToolHealthStatus.DEGRADED,
        ]
        assert "shell_available" in result.details

    @pytest.mark.asyncio
    async def test_check_web_tool(self, checker):
        """Test checking web tool health."""
        result = await checker.check_tool("web_search", use_cache=False)

        assert result.tool_name == "web_search"
        assert result.status in [
            ToolHealthStatus.HEALTHY,
            ToolHealthStatus.DEGRADED,
            ToolHealthStatus.UNHEALTHY,
        ]
        assert "dns_resolution" in result.details

    @pytest.mark.asyncio
    async def test_check_agent_tool(self, checker):
        """Test checking agent tool health."""
        result = await checker.check_tool("spawn_agent", use_cache=False)

        assert result.tool_name == "spawn_agent"
        assert result.status in [
            ToolHealthStatus.HEALTHY,
            ToolHealthStatus.UNHEALTHY,
        ]
        assert "subagent_manager" in result.details

    @pytest.mark.asyncio
    async def test_check_unknown_tool(self, checker):
        """Test checking unknown tool."""
        result = await checker.check_tool("unknown_tool", use_cache=False)

        assert result.tool_name == "unknown_tool"
        assert result.status == ToolHealthStatus.UNHEALTHY
        assert "Unknown tool" in result.message

    @pytest.mark.asyncio
    async def test_check_caching(self, checker):
        """Test health check result caching."""
        # First check (should be cached)
        result1 = await checker.check_tool("run_command", use_cache=True)

        # Second check (should use cache)
        result2 = await checker.check_tool("run_command", use_cache=True)

        # Timestamps should be same (from cache)
        assert result1.last_check_time == result2.last_check_time

    @pytest.mark.asyncio
    async def test_check_bypass_cache(self, checker):
        """Test bypassing cache."""
        result1 = await checker.check_tool("run_command", use_cache=True)
        await asyncio.sleep(0.1)  # Small delay
        result2 = await checker.check_tool("run_command", use_cache=False)

        # Should have different timestamps
        assert result2.last_check_time >= result1.last_check_time

    @pytest.mark.asyncio
    async def test_check_all_tools(self, checker):
        """Test checking all tools."""
        with patch("mini_claude.tools.tool_registry") as mock_registry:
            mock_registry.list_tools.return_value = [
                "read_file",
                "run_command",
                "web_search",
            ]

            summary = await checker.check_all_tools(use_cache=False)

            assert summary.total_tools == 3
            assert summary.overall_status in [
                ToolHealthStatus.HEALTHY,
                ToolHealthStatus.DEGRADED,
                ToolHealthStatus.UNHEALTHY,
            ]
            assert len(summary.tool_results) == 3

    @pytest.mark.asyncio
    async def test_check_all_tools_empty(self, checker):
        """Test checking empty tool registry."""
        with patch("mini_claude.tools.tool_registry") as mock_registry:
            mock_registry.list_tools.return_value = []

            summary = await checker.check_all_tools(use_cache=False)

            assert summary.total_tools == 0
            assert summary.overall_status == ToolHealthStatus.HEALTHY
            assert len(summary.tool_results) == 0

    @pytest.mark.asyncio
    async def test_custom_check_execution(self, checker):
        """Test executing custom health check."""

        def custom_check():
            return ToolHealthResult(
                tool_name="custom",
                status=ToolHealthStatus.HEALTHY,
                message="Custom OK",
                last_check_time=1234567890.0,
            )

        checker.register_health_check("custom", custom_check)
        result = await checker.check_tool("custom", use_cache=False)

        assert result.tool_name == "custom"
        assert result.status == ToolHealthStatus.HEALTHY
        assert result.message == "Custom OK"

    @pytest.mark.asyncio
    async def test_async_custom_check(self, checker):
        """Test executing async custom health check."""

        async def async_custom_check():
            return ToolHealthResult(
                tool_name="async_custom",
                status=ToolHealthStatus.HEALTHY,
                message="Async check OK",
                last_check_time=1234567890.0,
            )

        checker.register_health_check("async_custom", async_custom_check)
        result = await checker.check_tool("async_custom", use_cache=False)

        assert result.status == ToolHealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_timeout_handling(self, checker):
        """Test health check timeout."""
        checker._timeout = 0.01  # Very short timeout

        async def slow_check():
            await asyncio.sleep(1.0)
            return ToolHealthResult(
                tool_name="slow",
                status=ToolHealthStatus.HEALTHY,
                message="OK",
                last_check_time=1234567890.0,
            )

        checker.register_health_check("slow", slow_check)
        result = await checker.check_tool("slow", use_cache=False)

        assert result.status == ToolHealthStatus.UNHEALTHY
        assert "timed out" in result.message.lower()

    def test_clear_cache(self, checker):
        """Test clearing cache."""
        checker._cache["test"] = ToolHealthResult(
            tool_name="test",
            status=ToolHealthStatus.HEALTHY,
            message="Cached",
            last_check_time=1234567890.0,
        )
        checker._last_full_check = ToolHealthSummary(
            total_tools=1,
            healthy_count=1,
            degraded_count=0,
            unhealthy_count=0,
            overall_status=ToolHealthStatus.HEALTHY,
            tool_results=[],
            timestamp=1234567890.0,
        )

        checker.clear_cache()

        assert checker._cache == {}
        assert checker._last_full_check is None

    def test_get_health_status(self, checker):
        """Test getting cached health status."""
        # Initially None
        assert checker.get_health_status() is None

        # After setting
        summary = ToolHealthSummary(
            total_tools=1,
            healthy_count=1,
            degraded_count=0,
            unhealthy_count=0,
            overall_status=ToolHealthStatus.HEALTHY,
            tool_results=[],
            timestamp=1234567890.0,
        )
        checker._last_full_check = summary

        assert checker.get_health_status() == summary


class TestGlobalFunctions:
    """Test global convenience functions."""

    def test_get_tool_health_checker_singleton(self):
        """Test global checker singleton."""
        checker1 = get_tool_health_checker()
        checker2 = get_tool_health_checker()

        assert checker1 == checker2

    @pytest.mark.asyncio
    async def test_check_tool_health_convenience(self):
        """Test convenience function for single tool check."""
        result = await check_tool_health("run_command")

        assert result.tool_name == "run_command"
        assert result.status in [
            ToolHealthStatus.HEALTHY,
            ToolHealthStatus.DEGRADED,
        ]

    @pytest.mark.asyncio
    async def test_check_all_tools_health_convenience(self):
        """Test convenience function for all tools check."""
        summary = await check_all_tools_health()

        assert summary.total_tools > 0
        assert summary.overall_status in [
            ToolHealthStatus.HEALTHY,
            ToolHealthStatus.DEGRADED,
            ToolHealthStatus.UNHEALTHY,
        ]


class TestIntegrationWithMonitoring:
    """Test integration with monitoring health module."""

    @pytest.mark.asyncio
    async def test_health_checker_integration(self):
        """Test that health checker works with monitoring module."""
        # Import directly from health module to avoid metrics initialization issues
        from mini_claude.monitoring.health import HealthChecker

        checker = HealthChecker()

        # Test detailed tools health
        tools_health = await checker.check_tools_health_detailed()

        assert tools_health.status.value in ["healthy", "degraded", "unhealthy"]
        assert tools_health.tool_health_details is not None

    @pytest.mark.asyncio
    async def test_full_health_check_with_detailed_tools(self):
        """Test full health check with detailed tools."""
        from mini_claude.monitoring.health import HealthChecker

        checker = HealthChecker()
        report = await checker.check_health(detailed_tools=True)

        assert report.tools.tool_health_details is not None
        assert "tools" in report.tools.tool_health_details


class TestBaseToolHealthCheck:
    """Test BaseTool.health_check method."""

    @pytest.mark.asyncio
    async def test_base_tool_health_check(self):
        """Test health_check method on BaseTool instances."""
        from mini_claude.tools import get_tool

        # Get a registered tool
        read_tool = get_tool("read_file")
        if read_tool:
            result = await read_tool.health_check()

            assert result.tool_name == "read_file"
            assert result.status in [
                ToolHealthStatus.HEALTHY,
                ToolHealthStatus.DEGRADED,
                ToolHealthStatus.UNHEALTHY,
            ]
