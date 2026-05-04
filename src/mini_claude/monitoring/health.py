"""Health check system for monitoring service status.

Provides health check endpoints and utilities for monitoring:
- Service status (uptime, memory usage)
- Model connection (LLM provider availability)
- Tool availability (registered tools status)
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import psutil

from mini_claude.config.settings import settings
from mini_claude.tools import tool_registry


class HealthStatus(str, Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


@dataclass
class ServiceHealth:
    """Service health information."""

    status: HealthStatus
    uptime_seconds: float
    memory_usage_mb: float
    version: str = "1.0.0"
    cpu_percent: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "uptime_human": self._format_uptime(self.uptime_seconds),
            "memory_usage_mb": round(self.memory_usage_mb, 2),
            "version": self.version,
            "cpu_percent": round(self.cpu_percent, 1),
        }

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """Format uptime in human-readable format."""
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        return f"{secs}s"


@dataclass
class ModelHealth:
    """Model (LLM) health information."""

    status: HealthStatus
    model_name: str
    provider: str
    last_check_time: float
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data: Dict[str, Any] = {
            "status": self.status.value,
            "model_name": self.model_name,
            "provider": self.provider,
            "last_check_time": datetime.fromtimestamp(self.last_check_time).isoformat(),
        }
        if self.response_time_ms is not None:
            data["response_time_ms"] = round(self.response_time_ms, 2)
        if self.error_message:
            data["error_message"] = self.error_message
        return data


@dataclass
class ToolHealth:
    """Tool registry health information."""

    status: HealthStatus
    total_tools: int
    available_tools: int
    tool_names: List[str] = field(default_factory=list)
    unavailable_tools: List[str] = field(default_factory=list)
    tool_health_details: Optional[Dict[str, Any]] = None  # Detailed health per tool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {
            "status": self.status.value,
            "total_tools": self.total_tools,
            "available_tools": self.available_tools,
            "tool_names": self.tool_names,
            "unavailable_tools": self.unavailable_tools,
        }
        if self.tool_health_details:
            data["tool_health_details"] = self.tool_health_details
        return data


@dataclass
class HealthReport:
    """Complete health report."""

    service: ServiceHealth
    model: ModelHealth
    tools: ToolHealth
    timestamp: float

    def overall_status(self) -> HealthStatus:
        """Determine overall health status.

        Priority: UNHEALTHY > DEGRADED > HEALTHY
        """
        if any(
            h == HealthStatus.UNHEALTHY
            for h in [self.service.status, self.model.status, self.tools.status]
        ):
            return HealthStatus.UNHEALTHY
        if any(
            h == HealthStatus.DEGRADED
            for h in [self.service.status, self.model.status, self.tools.status]
        ):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "overall_status": self.overall_status().value,
            "service": self.service.to_dict(),
            "model": self.model.to_dict(),
            "tools": self.tools.to_dict(),
            "timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


class HealthChecker:
    """Health checker for monitoring service status."""

    def __init__(
        self,
        version: str = "1.0.0",
        model_name: Optional[str] = None,
    ):
        """Initialize health checker.

        Args:
            version: Service version string.
            model_name: Model name to check (uses settings default if not provided).
        """
        self.version = version
        self.model_name = model_name or settings.default_model
        self.start_time = time.time()
        self._last_model_check: Optional[ModelHealth] = None

    def get_uptime(self) -> float:
        """Get service uptime in seconds."""
        return time.time() - self.start_time

    def get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)

    def get_cpu_percent(self) -> float:
        """Get current CPU usage percent."""
        process = psutil.Process(os.getpid())
        return process.cpu_percent(interval=0.1)

    def check_service_health(self) -> ServiceHealth:
        """Check service health.

        Returns:
            ServiceHealth with current status.
        """
        memory_mb = self.get_memory_usage()
        cpu_percent = self.get_cpu_percent()
        uptime = self.get_uptime()

        # Determine status based on resource usage
        if memory_mb > 1024 or cpu_percent > 90:  # > 1GB or > 90% CPU
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        return ServiceHealth(
            status=status,
            uptime_seconds=uptime,
            memory_usage_mb=memory_mb,
            version=self.version,
            cpu_percent=cpu_percent,
        )

    async def check_model_health(self) -> ModelHealth:
        """Check LLM model health by making a simple test call.

        Returns:
            ModelHealth with connection status.
        """
        from mini_claude.llm.provider import LLMProvider

        provider = settings.get_model_provider(self.model_name)

        try:
            llm = LLMProvider(self.model_name)

            start_time = time.time()

            # Simple test message
            response = await llm.chat(
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=10,
                temperature=0.1,
            )

            response_time_ms = (time.time() - start_time) * 1000

            # Check if we got a valid response
            if response and response.choices:
                return ModelHealth(
                    status=HealthStatus.HEALTHY,
                    model_name=self.model_name,
                    provider=provider.value,
                    response_time_ms=response_time_ms,
                    last_check_time=time.time(),
                )
            else:
                return ModelHealth(
                    status=HealthStatus.UNHEALTHY,
                    model_name=self.model_name,
                    provider=provider.value,
                    error_message="Empty response from model",
                    last_check_time=time.time(),
                )

        except Exception as e:
            error_msg = str(e)
            # Truncate long error messages
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."

            return ModelHealth(
                status=HealthStatus.UNHEALTHY,
                model_name=self.model_name,
                provider=provider.value,
                error_message=error_msg,
                last_check_time=time.time(),
            )

    def check_tools_health(self) -> ToolHealth:
        """Check tools registry health.

        Returns:
            ToolHealth with tool availability status.
        """
        tool_names = tool_registry.list_tools()
        total = len(tool_names)

        # All registered tools are considered available
        # (tool_registry.execute would raise if tool doesn't exist)
        available = total

        # Determine status
        if total == 0:
            status = HealthStatus.HEALTHY  # Empty registry is OK
        elif available < total:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        return ToolHealth(
            status=status,
            total_tools=total,
            available_tools=available,
            tool_names=tool_names,
            unavailable_tools=[],
        )

    async def check_tools_health_detailed(self) -> ToolHealth:
        """Check tools registry health with detailed per-tool status.

        Performs actual health checks on each tool to verify availability.

        Returns:
            ToolHealth with detailed tool health information.
        """
        from mini_claude.tools.health_check import get_tool_health_checker

        checker = get_tool_health_checker()
        summary = await checker.check_all_tools(use_cache=True)

        # Determine overall status
        if summary.unhealthy_count > 0:
            status = HealthStatus.UNHEALTHY
        elif summary.degraded_count > 0:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        # Build unavailable tools list (unhealthy status)
        unavailable = [
            r.tool_name for r in summary.tool_results
            if r.status.value == "unhealthy"
        ]

        return ToolHealth(
            status=status,
            total_tools=summary.total_tools,
            available_tools=summary.healthy_count + summary.degraded_count,
            tool_names=[r.tool_name for r in summary.tool_results],
            unavailable_tools=unavailable,
            tool_health_details=summary.to_dict(),
        )

    async def check_health(self, detailed_tools: bool = False) -> HealthReport:
        """Perform full health check.

        Args:
            detailed_tools: If True, perform detailed per-tool health checks.

        Returns:
            HealthReport with all component statuses.
        """
        # Run checks concurrently
        service_task = asyncio.create_task(asyncio.to_thread(self.check_service_health))
        model_task = asyncio.create_task(self.check_model_health())

        if detailed_tools:
            tools_task = asyncio.create_task(self.check_tools_health_detailed())
        else:
            tools_task = asyncio.create_task(asyncio.to_thread(self.check_tools_health))

        service_health, model_health, tools_health = await asyncio.gather(
            service_task, model_task, tools_task
        )

        return HealthReport(
            service=service_health,
            model=model_health,
            tools=tools_health,
            timestamp=time.time(),
        )


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get or create the global health checker instance.

    This function provides backward compatibility with existing code.
    New code should prefer ApplicationContext.health_checker.
    """
    global _health_checker
    if _health_checker is None:
        # Try to use ApplicationContext first
        try:
            from mini_claude.context import get_context
            ctx = get_context()
            if ctx._health_checker.is_initialized():
                _health_checker = ctx.health_checker
            else:
                _health_checker = HealthChecker()
                ctx.health_checker = _health_checker
        except ImportError:
            _health_checker = HealthChecker()
    return _health_checker


def reset_health_checker() -> None:
    """Reset the global health checker (for testing)."""
    global _health_checker
    _health_checker = None
    # Also reset in context
    try:
        from mini_claude.context import get_context
        ctx = get_context()
        ctx._health_checker.reset()
    except ImportError:
        pass


async def check_health() -> HealthReport:
    """Convenience function to perform health check.

    Returns:
        HealthReport with all component statuses.
    """
    checker = get_health_checker()
    return await checker.check_health()


# HTTP server for health endpoint
async def health_handler(request: Any) -> Any:
    """Handle /health HTTP request.

    Args:
        request: aiohttp request object.

    Returns:
        JSON response with health report.
    """
    import aiohttp.web as web

    report = await check_health()
    status_code = 200 if report.overall_status() == HealthStatus.HEALTHY else 503

    return web.Response(
        text=report.to_json(),
        content_type="application/json",
        status=status_code,
    )


async def readiness_handler(request: Any) -> Any:
    """Handle /ready HTTP request for Kubernetes readiness probe.

    Returns:
        JSON response indicating readiness.
    """
    import aiohttp.web as web

    report = await check_health()

    # For readiness, we only check if the service can handle requests
    # Model can be unhealthy and we still serve (degraded mode)
    if report.service.status == HealthStatus.HEALTHY:
        return web.Response(
            text=json.dumps({"ready": True}),
            content_type="application/json",
            status=200,
        )
    else:
        return web.Response(
            text=json.dumps({"ready": False, "reason": "Service not healthy"}),
            content_type="application/json",
            status=503,
        )


async def liveness_handler(request: Any) -> Any:
    """Handle /live HTTP request for Kubernetes liveness probe.

    Returns:
        JSON response indicating liveness.
    """
    import aiohttp.web as web

    # Liveness just checks if the process is alive
    return web.Response(
        text=json.dumps({"alive": True, "uptime": time.time() - get_health_checker().start_time}),
        content_type="application/json",
        status=200,
    )


async def run_health_server(
    port: int = 8080,
    host: str = "0.0.0.0",
    run: bool = True,
) -> Any:
    """Run health check HTTP server.

    Args:
        port: Port to listen on.
        host: Host to bind to.
        run: If True, run the server; if False, just create it.

    Returns:
        aiohttp Application instance.
    """
    import aiohttp.web as web

    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/healthz", health_handler)  # Kubernetes style
    app.router.add_get("/ready", readiness_handler)
    app.router.add_get("/readyz", readiness_handler)  # Kubernetes style
    app.router.add_get("/live", liveness_handler)
    app.router.add_get("/livez", liveness_handler)  # Kubernetes style

    if run:
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)

        print(f"Health check server running on http://{host}:{port}")
        print("Endpoints: /health, /ready, /live")

        await site.start()

        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)  # Sleep for an hour
        except asyncio.CancelledError:
            await runner.cleanup()

    return app
