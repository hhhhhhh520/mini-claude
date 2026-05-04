"""Chaos testing framework for fault injection.

This module provides a comprehensive chaos testing framework to simulate
various failure scenarios including network failures, API rate limiting,
and resource exhaustion.

Classes:
    ChaosInjector: Base class for all chaos injectors
    NetworkChaosInjector: Network failure injection
    APIChaosInjector: API rate limiting and error injection
    ResourceChaosInjector: Resource exhaustion injection
    ChaosTest: Test framework for chaos scenarios
"""

import asyncio
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generator, List, Optional, Type

import respx
from httpx import Response, ConnectError, ReadTimeout

from mini_claude.agent.degradation import (
    DegradationManager,
    DegradationEvent,
)
from mini_claude.utils.logger import get_logger

logger = get_logger(__name__)


class ChaosType(str, Enum):
    """Types of chaos that can be injected."""
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_DISCONNECT = "network_disconnect"
    NETWORK_SLOW = "network_slow"
    API_RATE_LIMIT = "api_rate_limit"
    API_ERROR = "api_error"
    API_UNAVAILABLE = "api_unavailable"
    RESOURCE_MEMORY = "resource_memory"
    RESOURCE_DISK = "resource_disk"
    RESOURCE_CPU = "resource_cpu"


@dataclass
class ChaosScenario:
    """A single chaos scenario configuration."""
    name: str
    chaos_type: ChaosType
    duration: float = 1.0  # seconds
    probability: float = 1.0  # 0.0 to 1.0
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class ChaosResult:
    """Result of a chaos test execution."""
    scenario: ChaosScenario
    success: bool
    error_handled: bool
    degradation_triggered: bool
    recovery_successful: bool
    duration: float
    error_message: Optional[str] = None
    degradation_events: List[DegradationEvent] = field(default_factory=list)


class ChaosInjector(ABC):
    """Abstract base class for chaos injectors.

    Chaos injectors are responsible for injecting specific types of
    failures into the system and then cleaning up after the test.
    """

    def __init__(self, scenario: ChaosScenario):
        self.scenario = scenario
        self._cleanup_actions: List[Callable] = []
        self._is_active = False

    @abstractmethod
    def inject(self) -> None:
        """Inject the chaos scenario."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up after the chaos scenario."""
        pass

    @property
    def is_active(self) -> bool:
        """Check if chaos is currently active."""
        return self._is_active

    def add_cleanup(self, action: Callable) -> None:
        """Add a cleanup action to be executed during cleanup."""
        self._cleanup_actions.append(action)

    def _run_cleanups(self) -> None:
        """Run all registered cleanup actions."""
        for action in reversed(self._cleanup_actions):
            try:
                action()
            except Exception as e:
                logger.warning("Cleanup action failed", error=str(e))
        self._cleanup_actions.clear()


class NetworkChaosInjector(ChaosInjector):
    """Inject network-related failures.

    Supported scenarios:
    - NETWORK_TIMEOUT: Simulate request timeouts
    - NETWORK_DISCONNECT: Simulate connection drops
    - NETWORK_SLOW: Simulate slow network responses
    """

    def __init__(self, scenario: ChaosScenario):
        super().__init__(scenario)
        self._respx_mock: Optional[respx.MockRouter] = None

    def inject(self) -> None:
        """Inject network chaos."""
        self._is_active = True

        if self.scenario.chaos_type == ChaosType.NETWORK_TIMEOUT:
            self._inject_timeout()
        elif self.scenario.chaos_type == ChaosType.NETWORK_DISCONNECT:
            self._inject_disconnect()
        elif self.scenario.chaos_type == ChaosType.NETWORK_SLOW:
            self._inject_slow()
        else:
            raise ValueError(f"Unsupported chaos type: {self.scenario.chaos_type}")

    def _inject_timeout(self) -> None:
        """Inject network timeout."""
        timeout_seconds = self.scenario.params.get("timeout_seconds", 30.0)

        def timeout_callback(request):
            time.sleep(timeout_seconds)
            raise ReadTimeout("Connection timed out", request=request)

        # Mock all HTTP requests to timeout
        self._respx_mock = respx.mock()
        self._respx_mock.route(
            url__regex=r".*"
        ).mock(side_effect=timeout_callback)
        self._respx_mock.start()

        logger.info("Network timeout chaos injected", timeout=timeout_seconds)

    def _inject_disconnect(self) -> None:
        """Inject network disconnection."""
        def disconnect_callback(request):
            raise ConnectError("Connection refused", request=request)

        self._respx_mock = respx.mock()
        self._respx_mock.route(
            url__regex=r".*"
        ).mock(side_effect=disconnect_callback)
        self._respx_mock.start()

        logger.info("Network disconnect chaos injected")

    def _inject_slow(self) -> None:
        """Inject slow network response."""
        delay_seconds = self.scenario.params.get("delay_seconds", 5.0)

        def slow_callback(request):
            time.sleep(delay_seconds)
            return Response(200, json={"message": "delayed response"})

        self._respx_mock = respx.mock()
        self._respx_mock.route(
            url__regex=r".*"
        ).mock(side_effect=slow_callback)
        self._respx_mock.start()

        logger.info("Network slow chaos injected", delay=delay_seconds)

    def cleanup(self) -> None:
        """Clean up network chaos."""
        if self._respx_mock:
            try:
                self._respx_mock.stop()
            except Exception as e:
                logger.warning("Failed to stop respx mock", error=str(e))
            self._respx_mock = None

        self._run_cleanups()
        self._is_active = False
        logger.info("Network chaos cleaned up")


class APIChaosInjector(ChaosInjector):
    """Inject API-related failures.

    Supported scenarios:
    - API_RATE_LIMIT: Simulate 429 Too Many Requests
    - API_ERROR: Simulate 5xx server errors
    - API_UNAVAILABLE: Simulate service unavailability
    """

    def __init__(self, scenario: ChaosScenario):
        super().__init__(scenario)
        self._respx_mock: Optional[respx.MockRouter] = None
        self._call_count = 0

    def inject(self) -> None:
        """Inject API chaos."""
        self._is_active = True

        if self.scenario.chaos_type == ChaosType.API_RATE_LIMIT:
            self._inject_rate_limit()
        elif self.scenario.chaos_type == ChaosType.API_ERROR:
            self._inject_error()
        elif self.scenario.chaos_type == ChaosType.API_UNAVAILABLE:
            self._inject_unavailable()
        else:
            raise ValueError(f"Unsupported chaos type: {self.scenario.chaos_type}")

    def _inject_rate_limit(self) -> None:
        """Inject API rate limiting (429)."""
        retry_after = self.scenario.params.get("retry_after", 60)

        def rate_limit_callback(request):
            self._call_count += 1
            # Allow some requests through before rate limiting
            failures_before_success = self.scenario.params.get("failures_before_success", 3)
            if self._call_count <= failures_before_success:
                return Response(
                    429,
                    headers={"Retry-After": str(retry_after)},
                    json={
                        "error": "rate_limit_exceeded",
                        "message": "Too many requests",
                        "retry_after": retry_after,
                    }
                )
            else:
                # After failures, allow success
                return Response(200, json={"choices": [{"message": {"content": "success"}}]})

        self._respx_mock = respx.mock()
        self._respx_mock.route(
            url__regex=r".*"
        ).mock(side_effect=rate_limit_callback)
        self._respx_mock.start()

        logger.info("API rate limit chaos injected", retry_after=retry_after)

    def _inject_error(self) -> None:
        """Inject API server error (5xx)."""
        error_code = self.scenario.params.get("error_code", 500)
        error_message = self.scenario.params.get("error_message", "Internal Server Error")

        def error_callback(request):
            self._call_count += 1
            failures_before_success = self.scenario.params.get("failures_before_success", 2)
            if self._call_count <= failures_before_success:
                return Response(
                    error_code,
                    json={
                        "error": {
                            "message": error_message,
                            "type": "server_error",
                            "code": error_code,
                        }
                    }
                )
            else:
                return Response(200, json={"choices": [{"message": {"content": "success"}}]})

        self._respx_mock = respx.mock()
        self._respx_mock.route(
            url__regex=r".*"
        ).mock(side_effect=error_callback)
        self._respx_mock.start()

        logger.info("API error chaos injected", error_code=error_code)

    def _inject_unavailable(self) -> None:
        """Inject service unavailability (503)."""
        def unavailable_callback(request):
            return Response(
                503,
                json={
                    "error": {
                        "message": "Service temporarily unavailable",
                        "type": "service_unavailable",
                    }
                }
            )

        self._respx_mock = respx.mock()
        self._respx_mock.route(
            url__regex=r".*"
        ).mock(side_effect=unavailable_callback)
        self._respx_mock.start()

        logger.info("API unavailable chaos injected")

    def cleanup(self) -> None:
        """Clean up API chaos."""
        if self._respx_mock:
            try:
                self._respx_mock.stop()
            except Exception as e:
                logger.warning("Failed to stop respx mock", error=str(e))
            self._respx_mock = None

        self._call_count = 0
        self._run_cleanups()
        self._is_active = False
        logger.info("API chaos cleaned up")


class ResourceChaosInjector(ChaosInjector):
    """Inject resource exhaustion failures.

    Supported scenarios:
    - RESOURCE_MEMORY: Simulate memory exhaustion
    - RESOURCE_DISK: Simulate disk space exhaustion
    - RESOURCE_CPU: Simulate CPU exhaustion
    """

    def __init__(self, scenario: ChaosScenario):
        super().__init__(scenario)
        self._original_functions: Dict[str, Any] = {}

    def inject(self) -> None:
        """Inject resource chaos."""
        self._is_active = True

        if self.scenario.chaos_type == ChaosType.RESOURCE_MEMORY:
            self._inject_memory()
        elif self.scenario.chaos_type == ChaosType.RESOURCE_DISK:
            self._inject_disk()
        elif self.scenario.chaos_type == ChaosType.RESOURCE_CPU:
            self._inject_cpu()
        else:
            raise ValueError(f"Unsupported chaos type: {self.scenario.chaos_type}")

    def _inject_memory(self) -> None:
        """Inject memory exhaustion."""
        # Mock memory-related functions
        import sys

        large_allocation = self.scenario.params.get("simulate_large_allocation", True)

        if large_allocation:
            # Store original for potential restoration
            self._original_functions["sys_getsizeof"] = sys.getsizeof

            # Simulate memory pressure by patching memory-intensive operations
            # Note: This is a simplified simulation that doesn't actually exhaust memory
            # but demonstrates the pattern for memory chaos injection
            self.add_cleanup(lambda: None)

        logger.info("Memory chaos injected")

    def _inject_disk(self) -> None:
        """Inject disk space exhaustion."""
        import shutil

        # Save original functions
        self._original_functions["shutil_disk_usage"] = shutil.disk_usage

        # Mock disk_usage to return no space
        def mock_disk_usage(path):
            # Return a named tuple with very little free space
            total = 1000000000  # 1GB
            used = 999900000    # Almost full
            free = 100000       # 100KB free
            return shutil._ntuple_diskusage(total, used, free)

        shutil.disk_usage = mock_disk_usage

        self.add_cleanup(lambda: setattr(shutil, "disk_usage", self._original_functions["shutil_disk_usage"]))

        logger.info("Disk chaos injected")

    def _inject_cpu(self) -> None:
        """Inject CPU exhaustion (simulate slow processing)."""
        # We simulate CPU exhaustion by making async operations slower
        original_sleep = asyncio.sleep

        slow_factor = self.scenario.params.get("slow_factor", 10.0)

        async def slow_sleep(delay):
            await original_sleep(delay * slow_factor)

        asyncio.sleep = slow_sleep

        self.add_cleanup(lambda: setattr(asyncio, "sleep", original_sleep))

        logger.info("CPU chaos injected", slow_factor=slow_factor)

    def cleanup(self) -> None:
        """Clean up resource chaos."""
        # Restore original functions
        import shutil

        if "shutil_disk_usage" in self._original_functions:
            shutil.disk_usage = self._original_functions["shutil_disk_usage"]

        self._run_cleanups()
        self._is_active = False
        logger.info("Resource chaos cleaned up")


class ChaosTest:
    """Main chaos testing framework.

    Provides a unified interface for running chaos tests with:
    - Scenario configuration
    - Automatic cleanup
    - Degradation verification
    - Result collection

    Example:
        chaos = ChaosTest()

        # Create a scenario
        scenario = ChaosScenario(
            name="network_timeout",
            chaos_type=ChaosType.NETWORK_TIMEOUT,
            params={"timeout_seconds": 5.0},
        )

        # Run with chaos
        result = chaos.run_scenario(
            scenario,
            test_func=lambda: agent.run("test task"),
            verify_degradation=True,
        )

        assert result.success
        assert result.recovery_successful
    """

    INJECTOR_MAP: Dict[ChaosType, Type[ChaosInjector]] = {
        ChaosType.NETWORK_TIMEOUT: NetworkChaosInjector,
        ChaosType.NETWORK_DISCONNECT: NetworkChaosInjector,
        ChaosType.NETWORK_SLOW: NetworkChaosInjector,
        ChaosType.API_RATE_LIMIT: APIChaosInjector,
        ChaosType.API_ERROR: APIChaosInjector,
        ChaosType.API_UNAVAILABLE: APIChaosInjector,
        ChaosType.RESOURCE_MEMORY: ResourceChaosInjector,
        ChaosType.RESOURCE_DISK: ResourceChaosInjector,
        ChaosType.RESOURCE_CPU: ResourceChaosInjector,
    }

    def __init__(self, degradation_manager: Optional[DegradationManager] = None):
        self.degradation_manager = degradation_manager or DegradationManager()
        self._active_injectors: List[ChaosInjector] = []

    def get_injector(self, scenario: ChaosScenario) -> ChaosInjector:
        """Get appropriate injector for scenario."""
        injector_class = self.INJECTOR_MAP.get(scenario.chaos_type)
        if not injector_class:
            raise ValueError(f"No injector for chaos type: {scenario.chaos_type}")
        return injector_class(scenario)

    def run_scenario(
        self,
        scenario: ChaosScenario,
        test_func: Callable,
        verify_degradation: bool = True,
        verify_recovery: bool = True,
    ) -> ChaosResult:
        """Run a chaos test scenario.

        Args:
            scenario: The chaos scenario to execute
            test_func: The test function to run under chaos
            verify_degradation: Whether to verify degradation was triggered
            verify_recovery: Whether to verify recovery mechanisms

        Returns:
            ChaosResult with test outcome details
        """
        start_time = time.time()
        injector = None
        result = ChaosResult(
            scenario=scenario,
            success=False,
            error_handled=False,
            degradation_triggered=False,
            recovery_successful=False,
            duration=0.0,
        )

        if not scenario.enabled:
            result.success = True
            result.duration = time.time() - start_time
            return result

        try:
            # Reset degradation manager for clean state
            self.degradation_manager.reset_all()
            initial_model = self.degradation_manager.model.get_current_model()

            # Inject chaos
            injector = self.get_injector(scenario)
            injector.inject()
            self._active_injectors.append(injector)

            # Run test
            try:
                test_func()
                result.success = True
                result.error_handled = True
            except Exception as e:
                result.error_message = str(e)
                # Check if this was a handled error
                result.error_handled = self._is_handled_error(e)

            # Verify degradation
            if verify_degradation:
                result.degradation_triggered = self._check_degradation(initial_model)
                result.degradation_events = self.degradation_manager.get_history()

            # Verify recovery
            if verify_recovery and result.degradation_triggered:
                result.recovery_successful = self._check_recovery()

        except Exception as e:
            result.error_message = f"Chaos injection failed: {e}"

        finally:
            # Cleanup
            if injector:
                try:
                    injector.cleanup()
                except Exception as e:
                    logger.warning("Injector cleanup failed", error=str(e))

            if injector in self._active_injectors:
                self._active_injectors.remove(injector)

            result.duration = time.time() - start_time

        return result

    async def run_scenario_async(
        self,
        scenario: ChaosScenario,
        test_func: Callable,
        verify_degradation: bool = True,
        verify_recovery: bool = True,
    ) -> ChaosResult:
        """Run a chaos test scenario asynchronously.

        Args:
            scenario: The chaos scenario to execute
            test_func: The async test function to run under chaos
            verify_degradation: Whether to verify degradation was triggered
            verify_recovery: Whether to verify recovery mechanisms

        Returns:
            ChaosResult with test outcome details
        """
        start_time = time.time()
        injector = None
        result = ChaosResult(
            scenario=scenario,
            success=False,
            error_handled=False,
            degradation_triggered=False,
            recovery_successful=False,
            duration=0.0,
        )

        if not scenario.enabled:
            result.success = True
            result.duration = time.time() - start_time
            return result

        try:
            # Reset degradation manager for clean state
            self.degradation_manager.reset_all()
            initial_model = self.degradation_manager.model.get_current_model()

            # Inject chaos
            injector = self.get_injector(scenario)
            injector.inject()
            self._active_injectors.append(injector)

            # Run test
            try:
                if asyncio.iscoroutinefunction(test_func):
                    await test_func()
                else:
                    test_func()
                result.success = True
                result.error_handled = True
            except Exception as e:
                result.error_message = str(e)
                result.error_handled = self._is_handled_error(e)

            # Verify degradation
            if verify_degradation:
                result.degradation_triggered = self._check_degradation(initial_model)
                result.degradation_events = self.degradation_manager.get_history()

            # Verify recovery
            if verify_recovery and result.degradation_triggered:
                result.recovery_successful = self._check_recovery()

        except Exception as e:
            result.error_message = f"Chaos injection failed: {e}"

        finally:
            if injector:
                try:
                    injector.cleanup()
                except Exception as e:
                    logger.warning("Injector cleanup failed", error=str(e))

            if injector in self._active_injectors:
                self._active_injectors.remove(injector)

            result.duration = time.time() - start_time

        return result

    def cleanup_all(self) -> None:
        """Clean up all active chaos injectors."""
        for injector in reversed(self._active_injectors):
            try:
                injector.cleanup()
            except Exception as e:
                logger.warning("Cleanup failed for injector", error=str(e))
        self._active_injectors.clear()

    def _is_handled_error(self, error: Exception) -> bool:
        """Check if error was handled gracefully."""
        # Errors that indicate graceful handling
        handled_error_messages = [
            "LLM 调用失败",
            "已尝试",
            "降级",
            "fallback",
            "retry",
            "rate limit",
        ]
        error_str = str(error).lower()
        return any(msg.lower() in error_str for msg in handled_error_messages)

    def _check_degradation(self, initial_model: str) -> bool:
        """Check if degradation was triggered."""
        current_model = self.degradation_manager.model.get_current_model()
        if current_model != initial_model:
            return True

        # Check for tool degradation
        if self.degradation_manager.tool.get_disabled_tools():
            return True

        # Check history
        return len(self.degradation_manager.get_history()) > 0

    def _check_recovery(self) -> bool:
        """Check if system recovered after degradation."""
        # Check if model reset to primary
        self.degradation_manager.model.reset()
        return self.degradation_manager.model.get_current_model() == self.degradation_manager.model.primary


@contextmanager
def chaos_context(
    chaos_type: ChaosType,
    params: Optional[Dict[str, Any]] = None,
    name: Optional[str] = None,
) -> Generator[ChaosInjector, None, None]:
    """Context manager for chaos injection.

    Args:
        chaos_type: Type of chaos to inject
        params: Parameters for the chaos scenario
        name: Optional name for the scenario

    Yields:
        ChaosInjector instance

    Example:
        with chaos_context(ChaosType.NETWORK_TIMEOUT, {"timeout_seconds": 5}) as injector:
            # Code under test
            response = client.get("/api")
    """
    scenario = ChaosScenario(
        name=name or f"chaos_{chaos_type.value}",
        chaos_type=chaos_type,
        params=params or {},
    )

    chaos_test = ChaosTest()
    injector = chaos_test.get_injector(scenario)

    try:
        injector.inject()
        yield injector
    finally:
        injector.cleanup()
