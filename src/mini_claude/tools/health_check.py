"""Tool health check system for monitoring tool availability.

Provides health checks for each tool type:
- File operations: check workspace directory access
- Bash commands: check shell availability
- Web tools: check network connectivity
- Agent tools: check sub-agent creation capability
"""

import asyncio
import os
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from mini_claude.config.settings import settings
from mini_claude.utils.logger import get_logger

logger = get_logger("mini_claude.tools.health_check")


class ToolHealthStatus(str, Enum):
    """Health status levels for tools."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ToolHealthResult:
    """Health check result for a single tool."""

    tool_name: str
    status: ToolHealthStatus
    message: str
    last_check_time: float
    details: Dict[str, Any] = field(default_factory=dict)
    response_time_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data: Dict[str, Any] = {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "message": self.message,
            "last_check_time": datetime.fromtimestamp(self.last_check_time).isoformat(),
        }
        if self.details:
            data["details"] = self.details
        if self.response_time_ms is not None:
            data["response_time_ms"] = round(self.response_time_ms, 2)
        return data


@dataclass
class ToolHealthSummary:
    """Summary of all tools health status."""

    total_tools: int
    healthy_count: int
    degraded_count: int
    unhealthy_count: int
    overall_status: ToolHealthStatus
    tool_results: List[ToolHealthResult]
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_tools": self.total_tools,
            "healthy_count": self.healthy_count,
            "degraded_count": self.degraded_count,
            "unhealthy_count": self.unhealthy_count,
            "overall_status": self.overall_status.value,
            "tools": [r.to_dict() for r in self.tool_results],
            "timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
        }


class ToolHealthChecker:
    """Health checker for monitoring tool availability.

    Features:
    - Check individual tools health status
    - Check all registered tools
    - Cache results to avoid frequent checks
    - Support async health checks
    - Allow custom health check registration
    """

    def __init__(
        self,
        cache_ttl_seconds: float = 30.0,
        timeout_seconds: float = 5.0,
    ):
        """Initialize tool health checker.

        Args:
            cache_ttl_seconds: Cache TTL for health check results.
            timeout_seconds: Timeout for individual health checks.
        """
        self._cache_ttl = cache_ttl_seconds
        self._timeout = timeout_seconds
        self._cache: Dict[str, ToolHealthResult] = {}
        self._custom_checks: Dict[str, Callable] = {}
        self._last_full_check: Optional[ToolHealthSummary] = None

    def register_health_check(
        self,
        tool_name: str,
        check_func: Callable[[], ToolHealthResult],
    ) -> None:
        """Register a custom health check function for a tool.

        Args:
            tool_name: Name of the tool.
            check_func: Async or sync function that returns ToolHealthResult.
        """
        self._custom_checks[tool_name] = check_func
        logger.debug("Registered custom health check", tool_name=tool_name)

    def _is_cache_valid(self, tool_name: str) -> bool:
        """Check if cached result is still valid."""
        if tool_name not in self._cache:
            return False

        cached = self._cache[tool_name]
        elapsed = time.time() - cached.last_check_time
        return elapsed < self._cache_ttl

    async def check_tool(self, tool_name: str, use_cache: bool = True) -> ToolHealthResult:
        """Check health status of a single tool.

        Args:
            tool_name: Name of the tool to check.
            use_cache: Whether to use cached result if available.

        Returns:
            ToolHealthResult with status details.
        """
        # Use cached result if valid
        if use_cache and self._is_cache_valid(tool_name):
            return self._cache[tool_name]

        # Run health check with timeout
        start_time = time.time()

        try:
            # Check if custom check registered
            if tool_name in self._custom_checks:
                check_func = self._custom_checks[tool_name]
                if asyncio.iscoroutinefunction(check_func):
                    result = await asyncio.wait_for(
                        check_func(),
                        timeout=self._timeout,
                    )
                else:
                    result = await asyncio.to_thread(check_func)
            else:
                # Run default check based on tool category
                result = await self._default_health_check(tool_name)

            result.response_time_ms = (time.time() - start_time) * 1000

        except asyncio.TimeoutError:
            result = ToolHealthResult(
                tool_name=tool_name,
                status=ToolHealthStatus.UNHEALTHY,
                message=f"Health check timed out after {self._timeout}s",
                last_check_time=time.time(),
            )
        except Exception as e:
            result = ToolHealthResult(
                tool_name=tool_name,
                status=ToolHealthStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                last_check_time=time.time(),
            )

        # Cache result
        self._cache[tool_name] = result
        return result

    async def _default_health_check(self, tool_name: str) -> ToolHealthResult:
        """Run default health check based on tool category.

        Args:
            tool_name: Name of the tool.

        Returns:
            ToolHealthResult based on tool category.
        """
        # File operation tools
        file_tools = [
            "read_file",
            "write_file",
            "edit_file",
            "list_dir",
            "search_files",
            "search_content",
            "list_locks",
            "force_write",
        ]

        # Bash/command tools
        command_tools = ["run_command", "run_background"]

        # Web tools
        web_tools = ["web_search", "web_fetch", "weather"]

        # Agent tools
        agent_tools = ["spawn_agent", "list_agents", "get_result", "spawn_parallel"]

        # Parallel execution tools
        parallel_tools = [
            "plan_parallel",
            "execute_parallel",
            "parallel_status",
            "aggregate_results",
        ]

        if tool_name in file_tools:
            return await self._check_file_tool_health(tool_name)

        elif tool_name in command_tools:
            return await self._check_command_tool_health(tool_name)

        elif tool_name in web_tools:
            return await self._check_web_tool_health(tool_name)

        elif tool_name in agent_tools:
            return await self._check_agent_tool_health(tool_name)

        elif tool_name in parallel_tools:
            return await self._check_parallel_tool_health(tool_name)

        else:
            # Unknown tool - mark as unhealthy
            return ToolHealthResult(
                tool_name=tool_name,
                status=ToolHealthStatus.UNHEALTHY,
                message="Unknown tool - no health check available",
                last_check_time=time.time(),
            )

    async def _check_file_tool_health(self, tool_name: str) -> ToolHealthResult:
        """Check file operation tool health.

        Verifies:
        - Workspace directory exists and accessible
        - File lock manager available
        """
        details: Dict[str, Any] = {}

        # Check workspace directory
        workspace = settings.workspace_root
        workspace_ok = os.path.isdir(workspace) and os.access(workspace, os.R_OK)

        details["workspace_path"] = workspace
        details["workspace_accessible"] = workspace_ok

        # Check write access for write tools
        if tool_name in ["write_file", "edit_file", "force_write"]:
            write_ok = os.access(workspace, os.W_OK)
            details["workspace_writable"] = write_ok

            if workspace_ok and write_ok:
                status = ToolHealthStatus.HEALTHY
                message = "Workspace accessible and writable"
            elif workspace_ok:
                status = ToolHealthStatus.DEGRADED
                message = "Workspace readable but not writable"
            else:
                status = ToolHealthStatus.UNHEALTHY
                message = "Workspace not accessible"
        else:
            # Read-only tools
            if workspace_ok:
                status = ToolHealthStatus.HEALTHY
                message = "Workspace accessible"
            else:
                status = ToolHealthStatus.UNHEALTHY
                message = "Workspace not accessible"

        return ToolHealthResult(
            tool_name=tool_name,
            status=status,
            message=message,
            last_check_time=time.time(),
            details=details,
        )

    async def _check_command_tool_health(self, tool_name: str) -> ToolHealthResult:
        """Check command execution tool health.

        Verifies:
        - Shell is available
        - Basic commands work
        """
        details: Dict[str, Any] = {}

        try:
            # Test basic shell command
            process = await asyncio.create_subprocess_shell(
                "echo 'health_check_test'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=2.0,
            )

            shell_ok = process.returncode == 0
            details["shell_available"] = shell_ok
            details["returncode"] = process.returncode

            if shell_ok:
                status = ToolHealthStatus.HEALTHY
                message = "Shell command execution available"
            else:
                status = ToolHealthStatus.DEGRADED
                message = "Shell available but command failed"

        except asyncio.TimeoutError:
            status = ToolHealthStatus.UNHEALTHY
            message = "Shell command timed out"
            details["shell_available"] = False

        except Exception as e:
            status = ToolHealthStatus.UNHEALTHY
            message = f"Shell not available: {e}"
            details["shell_available"] = False

        return ToolHealthResult(
            tool_name=tool_name,
            status=status,
            message=message,
            last_check_time=time.time(),
            details=details,
        )

    async def _check_web_tool_health(self, tool_name: str) -> ToolHealthResult:
        """Check web tool health.

        Verifies:
        - Network connectivity
        - External service reachable
        """
        details: Dict[str, Any] = {}

        # Check network connectivity
        try:
            # Test DNS resolution
            socket.gethostbyname("www.baidu.com")
            network_ok = True
            details["dns_resolution"] = "ok"

        except socket.gaierror:
            network_ok = False
            details["dns_resolution"] = "failed"

        # Test HTTP connectivity for web fetch/fetch tools
        if tool_name in ["web_fetch", "weather"]:
            try:
                import requests

                # Quick connectivity test to a reliable endpoint
                test_url = "https://www.baidu.com"
                resp = await asyncio.to_thread(
                    requests.head,
                    test_url,
                    timeout=3.0,
                    allow_redirects=True,
                )
                http_ok = resp.status_code < 400
                details["http_connectivity"] = http_ok

            except Exception:
                http_ok = False
                details["http_connectivity"] = False

            if network_ok and http_ok:
                status = ToolHealthStatus.HEALTHY
                message = "Network and HTTP connectivity available"
            elif network_ok:
                status = ToolHealthStatus.DEGRADED
                message = "DNS works but HTTP may be blocked"
            else:
                status = ToolHealthStatus.UNHEALTHY
                message = "Network connectivity unavailable"

        elif tool_name == "web_search":
            # Check ddgs library availability
            try:
                from ddgs import DDGS  # noqa: F401

                details["ddgs_available"] = True

                if network_ok:
                    status = ToolHealthStatus.HEALTHY
                    message = "Web search available (ddgs installed, network OK)"
                else:
                    status = ToolHealthStatus.DEGRADED
                    message = "ddgs available but network may be restricted"

            except ImportError:
                details["ddgs_available"] = False
                status = ToolHealthStatus.DEGRADED
                message = "ddgs not installed - run: pip install ddgs"

        else:
            # Generic web tool
            if network_ok:
                status = ToolHealthStatus.HEALTHY
                message = "Network connectivity available"
            else:
                status = ToolHealthStatus.UNHEALTHY
                message = "Network connectivity unavailable"

        return ToolHealthResult(
            tool_name=tool_name,
            status=status,
            message=message,
            last_check_time=time.time(),
            details=details,
        )

    async def _check_agent_tool_health(self, tool_name: str) -> ToolHealthResult:
        """Check agent spawning tool health.

        Verifies:
        - Subagent manager available
        - LLM provider available
        """
        details: Dict[str, Any] = {}

        try:
            from mini_claude.agent.subagent import subagent_manager  # noqa: F401

            details["subagent_manager"] = True

            # Check LLM provider (needed for sub-agents)
            from mini_claude.llm.provider import LLMProvider  # noqa: F401

            details["llm_provider"] = True

            status = ToolHealthStatus.HEALTHY
            message = "Sub-agent creation capability available"

        except ImportError as e:
            details["subagent_manager"] = False
            details["import_error"] = str(e)
            status = ToolHealthStatus.UNHEALTHY
            message = f"Agent dependencies unavailable: {e}"

        return ToolHealthResult(
            tool_name=tool_name,
            status=status,
            message=message,
            last_check_time=time.time(),
            details=details,
        )

    async def _check_parallel_tool_health(self, tool_name: str) -> ToolHealthResult:
        """Check parallel execution tool health.

        Verifies:
        - asyncio available
        - File lock manager available
        """
        details: Dict[str, Any] = {}

        # These are always available as they use standard library
        details["asyncio_available"] = True

        try:
            from mini_claude.utils.file_lock import file_lock_manager  # noqa: F401

            details["file_lock_manager"] = True
            status = ToolHealthStatus.HEALTHY
            message = "Parallel execution capability available"

        except ImportError:
            details["file_lock_manager"] = False
            status = ToolHealthStatus.DEGRADED
            message = "File lock manager unavailable"

        return ToolHealthResult(
            tool_name=tool_name,
            status=status,
            message=message,
            last_check_time=time.time(),
            details=details,
        )

    async def check_all_tools(
        self,
        use_cache: bool = True,
        tool_names: Optional[List[str]] = None,
    ) -> ToolHealthSummary:
        """Check health status of all tools.

        Args:
            use_cache: Whether to use cached results.
            tool_names: Specific tools to check (all if None).

        Returns:
            ToolHealthSummary with all tool statuses.
        """
        # Get tool list
        if tool_names is None:
            from mini_claude.tools import tool_registry

            tool_names = tool_registry.list_tools()

        if not tool_names:
            return ToolHealthSummary(
                total_tools=0,
                healthy_count=0,
                degraded_count=0,
                unhealthy_count=0,
                overall_status=ToolHealthStatus.HEALTHY,
                tool_results=[],
                timestamp=time.time(),
            )

        # Run all checks concurrently
        results = await asyncio.gather(
            *[self.check_tool(name, use_cache) for name in tool_names],
            return_exceptions=True,
        )

        # Process results
        tool_results: List[ToolHealthResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                tool_results.append(
                    ToolHealthResult(
                        tool_name=tool_names[i],
                        status=ToolHealthStatus.UNHEALTHY,
                        message=f"Check failed: {result}",
                        last_check_time=time.time(),
                    )
                )
            else:
                tool_results.append(result)

        # Count statuses
        healthy = sum(1 for r in tool_results if r.status == ToolHealthStatus.HEALTHY)
        degraded = sum(1 for r in tool_results if r.status == ToolHealthStatus.DEGRADED)
        unhealthy = sum(1 for r in tool_results if r.status == ToolHealthStatus.UNHEALTHY)

        # Determine overall status
        if unhealthy > 0:
            overall = ToolHealthStatus.UNHEALTHY
        elif degraded > 0:
            overall = ToolHealthStatus.DEGRADED
        else:
            overall = ToolHealthStatus.HEALTHY

        summary = ToolHealthSummary(
            total_tools=len(tool_results),
            healthy_count=healthy,
            degraded_count=degraded,
            unhealthy_count=unhealthy,
            overall_status=overall,
            tool_results=tool_results,
            timestamp=time.time(),
        )

        # Cache summary
        self._last_full_check = summary

        return summary

    def get_health_status(self) -> Optional[ToolHealthSummary]:
        """Get cached health status summary.

        Returns cached summary if available, otherwise None.
        Use check_all_tools() to get fresh status.
        """
        return self._last_full_check

    def clear_cache(self) -> None:
        """Clear all cached health check results."""
        self._cache.clear()
        self._last_full_check = None
        logger.debug("Health check cache cleared")


# Global tool health checker instance
_tool_health_checker: Optional[ToolHealthChecker] = None


def get_tool_health_checker() -> ToolHealthChecker:
    """Get or create the global tool health checker instance.

    This function provides backward compatibility with existing code.
    New code should prefer ApplicationContext.tool_health_checker.
    """
    global _tool_health_checker
    if _tool_health_checker is None:
        # Try to use ApplicationContext first
        try:
            from mini_claude.context import get_context

            ctx = get_context()
            if ctx._tool_health_checker.is_initialized():
                _tool_health_checker = ctx.tool_health_checker
            else:
                _tool_health_checker = ToolHealthChecker()
                ctx.tool_health_checker = _tool_health_checker
        except ImportError:
            _tool_health_checker = ToolHealthChecker()
    return _tool_health_checker


def reset_tool_health_checker() -> None:
    """Reset the global tool health checker (for testing)."""
    global _tool_health_checker
    _tool_health_checker = None
    # Also reset in context
    try:
        from mini_claude.context import get_context

        ctx = get_context()
        ctx._tool_health_checker.reset()
    except ImportError:
        pass


async def check_tool_health(tool_name: str) -> ToolHealthResult:
    """Convenience function to check a single tool's health.

    Args:
        tool_name: Name of the tool to check.

    Returns:
        ToolHealthResult with status details.
    """
    checker = get_tool_health_checker()
    return await checker.check_tool(tool_name)


async def check_all_tools_health() -> ToolHealthSummary:
    """Convenience function to check all tools' health.

    Returns:
        ToolHealthSummary with all tool statuses.
    """
    checker = get_tool_health_checker()
    return await checker.check_all_tools()
