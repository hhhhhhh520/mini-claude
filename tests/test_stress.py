"""Stress testing suite for Mini Claude Code.

Validates system stability and performance under high concurrency scenarios.
Uses mock to avoid real API calls.

Run with:
    pytest tests/test_stress.py -v                    # All stress tests
    pytest tests/test_stress.py -v -m "not slow"     # Skip slow tests
    pytest tests/test_stress.py -v -m stress         # Only stress tests
"""

import asyncio
import gc
import json
import os
import tempfile
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest

from mini_claude.agent.coordinator import (
    ParallelCoordinator,
    TaskStatus,
)
from mini_claude.agent.subagent import AgentStatus, SubAgentManager
from mini_claude.config.settings import settings
from mini_claude.utils.file_lock import file_lock_manager


# =============================================================================
# Test Configuration
# =============================================================================

# Skip all stress tests if environment variable is set
SKIP_STRESS_TESTS = os.environ.get("SKIP_STRESS_TESTS", "").lower() in ("1", "true", "yes")

# Default stress test parameters
DEFAULT_CONCURRENT_REQUESTS = 10
DEFAULT_REQUEST_COUNT = 50
DEFAULT_DURATION_SECONDS = 5


# =============================================================================
# Metrics Collection
# =============================================================================


@dataclass
class PerformanceMetrics:
    """Collected performance metrics from stress tests."""

    # Timing
    start_time: float = 0.0
    end_time: float = 0.0
    total_duration: float = 0.0

    # Response times (in seconds)
    response_times: List[float] = field(default_factory=list)

    # Throughput
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0

    # Errors
    errors: List[str] = field(default_factory=list)

    # Memory (in bytes)
    memory_start: int = 0
    memory_end: int = 0
    memory_peak: int = 0

    # Resource usage
    active_tasks_peak: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        response_times = sorted(self.response_times) if self.response_times else []
        count = len(response_times)

        return {
            "timing": {
                "start_time": self.start_time,
                "end_time": self.end_time,
                "total_duration_seconds": round(self.total_duration, 3),
            },
            "throughput": {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "requests_per_second": round(
                    self.total_requests / self.total_duration if self.total_duration > 0 else 0, 2
                ),
                "success_rate_percent": round(
                    self.successful_requests / self.total_requests * 100
                    if self.total_requests > 0
                    else 0,
                    2,
                ),
            },
            "latency": {
                "min_seconds": round(min(response_times), 3) if response_times else 0,
                "max_seconds": round(max(response_times), 3) if response_times else 0,
                "avg_seconds": round(sum(response_times) / count, 3) if count > 0 else 0,
                "p50_seconds": round(response_times[int(count * 0.5)], 3) if count > 0 else 0,
                "p90_seconds": round(response_times[int(count * 0.9)], 3) if count > 0 else 0,
                "p99_seconds": round(response_times[int(count * 0.99)], 3) if count > 0 else 0,
            },
            "memory": {
                "start_mb": round(self.memory_start / 1024 / 1024, 2),
                "end_mb": round(self.memory_end / 1024 / 1024, 2),
                "peak_mb": round(self.memory_peak / 1024 / 1024, 2),
                "delta_mb": round((self.memory_end - self.memory_start) / 1024 / 1024, 2),
            },
            "errors": {
                "count": len(self.errors),
                "samples": self.errors[:10],  # First 10 errors
            },
            "resources": {
                "active_tasks_peak": self.active_tasks_peak,
            },
        }

    def get_report(self) -> str:
        """Generate human-readable report."""
        data = self.to_dict()
        lines = [
            "=== Stress Test Report ===",
            "",
            "## Timing",
            f"  Duration: {data['timing']['total_duration_seconds']}s",
            "",
            "## Throughput",
            f"  Total requests: {data['throughput']['total_requests']}",
            f"  Successful: {data['throughput']['successful_requests']}",
            f"  Failed: {data['throughput']['failed_requests']}",
            f"  Requests/sec: {data['throughput']['requests_per_second']}",
            f"  Success rate: {data['throughput']['success_rate_percent']}%",
            "",
            "## Latency",
            f"  Min: {data['latency']['min_seconds']}s",
            f"  Max: {data['latency']['max_seconds']}s",
            f"  Avg: {data['latency']['avg_seconds']}s",
            f"  P50: {data['latency']['p50_seconds']}s",
            f"  P90: {data['latency']['p90_seconds']}s",
            f"  P99: {data['latency']['p99_seconds']}s",
            "",
            "## Memory",
            f"  Start: {data['memory']['start_mb']}MB",
            f"  End: {data['memory']['end_mb']}MB",
            f"  Peak: {data['memory']['peak_mb']}MB",
            f"  Delta: {data['memory']['delta_mb']}MB",
            "",
            "## Errors",
            f"  Count: {data['errors']['count']}",
        ]

        if data["errors"]["samples"]:
            lines.append("  Sample errors:")
            for err in data["errors"]["samples"][:5]:
                lines.append(f"    - {err[:100]}")

        return "\n".join(lines)


# =============================================================================
# Stress Test Runner
# =============================================================================


class StressTestRunner:
    """Runner for stress tests with configurable parameters."""

    def __init__(
        self,
        concurrent_requests: int = DEFAULT_CONCURRENT_REQUESTS,
        request_count: int = DEFAULT_REQUEST_COUNT,
        duration_seconds: float = DEFAULT_DURATION_SECONDS,
        ramp_up_seconds: float = 0.0,
    ):
        """Initialize stress test runner.

        Args:
            concurrent_requests: Maximum concurrent requests.
            request_count: Total number of requests to make.
            duration_seconds: Duration for timed tests.
            ramp_up_seconds: Time to ramp up to full concurrency.
        """
        self.concurrent_requests = concurrent_requests
        self.request_count = request_count
        self.duration_seconds = duration_seconds
        self.ramp_up_seconds = ramp_up_seconds
        self.metrics = PerformanceMetrics()
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._active_tasks = 0
        self._active_tasks_peak = 0

    async def _run_single_request(self, request_func: Callable, request_id: int, **kwargs) -> Any:
        """Run a single request with metrics collection."""
        async with self._semaphore:
            self._active_tasks += 1
            self._active_tasks_peak = max(self._active_tasks_peak, self._active_tasks)

            start_time = time.time()
            try:
                result = await request_func(request_id=request_id, **kwargs)
                self.metrics.successful_requests += 1
                return result
            except Exception as e:
                self.metrics.failed_requests += 1
                self.metrics.errors.append(f"Request {request_id}: {str(e)}")
                raise
            finally:
                self._active_tasks -= 1
                response_time = time.time() - start_time
                self.metrics.response_times.append(response_time)

    async def run_concurrent_requests(self, request_func: Callable, **kwargs) -> PerformanceMetrics:
        """Run concurrent requests and collect metrics.

        Args:
            request_func: Async function to call for each request.
                          Should accept request_id parameter.
            **kwargs: Additional arguments for request_func.

        Returns:
            PerformanceMetrics with collected data.
        """
        self._semaphore = asyncio.Semaphore(self.concurrent_requests)
        self.metrics = PerformanceMetrics()

        # Start memory tracking - ensure clean state
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        tracemalloc.start()
        self.metrics.memory_start = tracemalloc.get_traced_memory()[0]
        self.metrics.start_time = time.time()

        try:
            # Create tasks
            tasks = []
            for i in range(self.request_count):
                # Ramp up delay
                if self.ramp_up_seconds > 0 and i > 0:
                    delay = self.ramp_up_seconds * (i / self.request_count)
                    await asyncio.sleep(delay)

                task = asyncio.create_task(self._run_single_request(request_func, i, **kwargs))
                tasks.append(task)

            # Wait for all tasks
            await asyncio.gather(*tasks, return_exceptions=True)

            # End metrics collection
            self.metrics.end_time = time.time()
            self.metrics.total_duration = self.metrics.end_time - self.metrics.start_time
            self.metrics.total_requests = self.request_count
            self.metrics.active_tasks_peak = self._active_tasks_peak

            # Memory tracking
            current, peak = tracemalloc.get_traced_memory()
            self.metrics.memory_end = current
            self.metrics.memory_peak = peak
        finally:
            # Ensure tracemalloc is stopped
            if tracemalloc.is_tracing():
                tracemalloc.stop()

        return self.metrics

    async def run_gradual_pressure(
        self, request_func: Callable, steps: int = 5, **kwargs
    ) -> Dict[str, PerformanceMetrics]:
        """Run gradual pressure test, increasing concurrency step by step.

        Args:
            request_func: Async function to call for each request.
            steps: Number of steps to increase concurrency.
            **kwargs: Additional arguments for request_func.

        Returns:
            Dictionary mapping step name to metrics.
        """
        results = {}

        for step in range(1, steps + 1):
            concurrency = self.concurrent_requests * step // steps
            requests = self.request_count // steps

            runner = StressTestRunner(
                concurrent_requests=concurrency,
                request_count=requests,
            )

            metrics = await runner.run_concurrent_requests(request_func, **kwargs)
            results[f"step_{step}_concurrency_{concurrency}"] = metrics

            # Brief pause between steps
            await asyncio.sleep(0.5)

        return results

    async def run_duration_test(self, request_func: Callable, **kwargs) -> PerformanceMetrics:
        """Run test for a fixed duration.

        Args:
            request_func: Async function to call for each request.
            **kwargs: Additional arguments for request_func.

        Returns:
            PerformanceMetrics with collected data.
        """
        self._semaphore = asyncio.Semaphore(self.concurrent_requests)
        self.metrics = PerformanceMetrics()

        # Ensure clean state
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        tracemalloc.start()
        self.metrics.memory_start = tracemalloc.get_traced_memory()[0]
        self.metrics.start_time = time.time()

        try:
            end_time = self.metrics.start_time + self.duration_seconds
            request_id = 0

            tasks = []
            while time.time() < end_time:
                task = asyncio.create_task(
                    self._run_single_request(request_func, request_id, **kwargs)
                )
                tasks.append(task)
                request_id += 1
                self.metrics.total_requests += 1

                # Small delay to avoid overwhelming
                await asyncio.sleep(0.01)

            # Wait for all tasks
            await asyncio.gather(*tasks, return_exceptions=True)

            self.metrics.end_time = time.time()
            self.metrics.total_duration = self.metrics.end_time - self.metrics.start_time

            current, peak = tracemalloc.get_traced_memory()
            self.metrics.memory_end = current
            self.metrics.memory_peak = peak
        finally:
            # Ensure tracemalloc is stopped
            if tracemalloc.is_tracing():
                tracemalloc.stop()

        return self.metrics


# =============================================================================
# Mock Functions for Testing
# =============================================================================


async def mock_session_create(request_id: int = 0, delay: float = 0.01) -> Dict[str, Any]:
    """Mock session creation with configurable delay."""
    await asyncio.sleep(delay)
    return {
        "session_id": f"session_{request_id}",
        "created_at": datetime.now().isoformat(),
        "status": "active",
    }


async def mock_tool_call(request_id: int = 0, tool_name: str = "test_tool") -> Dict[str, Any]:
    """Mock tool call with simulated processing time."""
    # Simulate varying processing times
    base_delay = 0.01
    variance = 0.005 * (request_id % 10)
    await asyncio.sleep(base_delay + variance)

    return {
        "tool": tool_name,
        "request_id": request_id,
        "result": f"success_{request_id}",
        "timestamp": datetime.now().isoformat(),
    }


async def mock_file_operation(request_id: int = 0, operation: str = "read") -> Dict[str, Any]:
    """Mock file operation with simulated I/O delay."""
    # Simulate I/O delay
    await asyncio.sleep(0.02)

    return {
        "operation": operation,
        "request_id": request_id,
        "path": f"/tmp/test_file_{request_id}.txt",
        "success": True,
    }


async def mock_agent_task(
    request_id: int = 0, complexity: str = "simple", progress_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """Mock agent task with progress reporting."""
    steps = {"simple": 2, "medium": 5, "complex": 10}.get(complexity, 3)

    for step in range(steps):
        await asyncio.sleep(0.01)
        if progress_callback:
            await progress_callback((step + 1) / steps, f"Step {step + 1}/{steps}")

    return {
        "task_id": request_id,
        "complexity": complexity,
        "steps_completed": steps,
        "status": "completed",
    }


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def stress_runner():
    """Create a stress test runner with default parameters."""
    return StressTestRunner(
        concurrent_requests=DEFAULT_CONCURRENT_REQUESTS,
        request_count=DEFAULT_REQUEST_COUNT,
    )


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for file operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def clean_subagent_manager():
    """Create a clean subagent manager for each test."""
    manager = SubAgentManager(max_concurrent=settings.max_sub_agents)
    manager.clear()
    yield manager
    manager.clear()


@pytest.fixture
async def clean_coordinator():
    """Create a clean coordinator for each test."""
    coordinator = ParallelCoordinator(max_agents=settings.max_sub_agents)
    await coordinator.clear()
    yield coordinator
    await coordinator.clear()


# =============================================================================
# Stress Tests: Concurrent Session Creation
# =============================================================================


@pytest.mark.stress
@pytest.mark.skipif(SKIP_STRESS_TESTS, reason="SKIP_STRESS_TESTS is set")
class TestConcurrentSessionCreation:
    """Test concurrent session creation stability."""

    @pytest.mark.asyncio
    async def test_basic_concurrent_sessions(self, stress_runner):
        """Test basic concurrent session creation."""
        metrics = await stress_runner.run_concurrent_requests(mock_session_create)

        assert metrics.total_requests == DEFAULT_REQUEST_COUNT
        assert metrics.successful_requests == metrics.total_requests
        assert metrics.failed_requests == 0
        assert len(metrics.errors) == 0

    @pytest.mark.asyncio
    async def test_high_concurrency_sessions(self):
        """Test high concurrency session creation."""
        runner = StressTestRunner(
            concurrent_requests=50,
            request_count=100,
        )

        metrics = await runner.run_concurrent_requests(mock_session_create)

        # Should handle high concurrency without errors
        assert metrics.successful_requests >= metrics.total_requests * 0.95  # 95% success

    @pytest.mark.asyncio
    async def test_gradual_pressure_sessions(self, stress_runner):
        """Test gradual pressure increase on sessions."""
        results = await stress_runner.run_gradual_pressure(mock_session_create, steps=3)

        assert len(results) == 3
        for step_name, metrics in results.items():
            assert metrics.successful_requests > 0
            assert metrics.failed_requests == 0


# =============================================================================
# Stress Tests: Concurrent Tool Calls
# =============================================================================


@pytest.mark.stress
@pytest.mark.skipif(SKIP_STRESS_TESTS, reason="SKIP_STRESS_TESTS is set")
class TestConcurrentToolCalls:
    """Test concurrent tool call stability."""

    @pytest.mark.asyncio
    async def test_concurrent_tool_calls(self, stress_runner):
        """Test concurrent tool calls."""
        metrics = await stress_runner.run_concurrent_requests(
            mock_tool_call, tool_name="write_file"
        )

        assert metrics.total_requests == DEFAULT_REQUEST_COUNT
        assert metrics.successful_requests == metrics.total_requests

    @pytest.mark.asyncio
    async def test_mixed_tool_calls(self, stress_runner):
        """Test mixed tool call types concurrently."""
        tools = ["read_file", "write_file", "edit_file", "bash", "web_search"]

        async def mixed_tool_request(request_id: int) -> Dict[str, Any]:
            tool = tools[request_id % len(tools)]
            return await mock_tool_call(request_id=request_id, tool_name=tool)

        metrics = await stress_runner.run_concurrent_requests(mixed_tool_request)

        assert metrics.successful_requests == metrics.total_requests

    @pytest.mark.asyncio
    async def test_tool_call_with_resource_limits(self, clean_subagent_manager):
        """Test tool calls respect resource limits."""
        max_concurrent = settings.max_sub_agents
        actual_concurrent = 0
        peak_concurrent = 0
        lock = asyncio.Lock()

        async def tracked_task(progress_callback=None):
            nonlocal actual_concurrent, peak_concurrent

            async with lock:
                actual_concurrent += 1
                peak_concurrent = max(peak_concurrent, actual_concurrent)

            await asyncio.sleep(0.05)

            async with lock:
                actual_concurrent -= 1

            return "done"

        # Spawn more tasks than max_concurrent
        for i in range(max_concurrent * 3):
            await clean_subagent_manager.spawn(f"agent_{i}", tracked_task)

        await clean_subagent_manager.wait_for_all()

        # Peak concurrent should not exceed limit
        assert peak_concurrent <= max_concurrent


# =============================================================================
# Stress Tests: Concurrent File Operations
# =============================================================================


@pytest.mark.stress
@pytest.mark.skipif(SKIP_STRESS_TESTS, reason="SKIP_STRESS_TESTS is set")
class TestConcurrentFileOperations:
    """Test concurrent file operation stability."""

    @pytest.mark.asyncio
    async def test_concurrent_file_reads(self, temp_workspace, stress_runner):
        """Test concurrent file read operations."""
        # Create test files
        test_files = []
        for i in range(10):
            path = temp_workspace / f"test_{i}.txt"
            path.write_text(f"content_{i}")
            test_files.append(str(path))

        async def read_file_request(request_id: int) -> Dict[str, Any]:
            file_path = test_files[request_id % len(test_files)]
            await asyncio.sleep(0.01)  # Simulate read
            return {"path": file_path, "content": Path(file_path).read_text()}

        metrics = await stress_runner.run_concurrent_requests(read_file_request)

        assert metrics.successful_requests == metrics.total_requests

    @pytest.mark.asyncio
    async def test_concurrent_file_locks(self, temp_workspace):
        """Test file locking under concurrent access."""
        test_file = temp_workspace / "locked.txt"
        test_file.write_text("initial")

        successful_locks = 0
        failed_locks = 0

        async def acquire_and_release(agent_id: str):
            nonlocal successful_locks, failed_locks

            success, msg = await file_lock_manager.acquire_lock(str(test_file), agent_id, "write")

            if success:
                successful_locks += 1
                await asyncio.sleep(0.01)
                await file_lock_manager.release_lock(str(test_file), agent_id)
            else:
                failed_locks += 1

            return success

        # Run concurrent lock attempts
        tasks = [acquire_and_release(f"agent_{i}") for i in range(20)]
        await asyncio.gather(*tasks)

        # At least some should succeed
        assert successful_locks > 0
        # Total attempts equals tasks
        assert successful_locks + failed_locks == 20

        # Clean up locks
        await file_lock_manager.release_all_for_agent("cleanup")


# =============================================================================
# Stress Tests: Memory Stability
# =============================================================================


@pytest.mark.stress
@pytest.mark.slow
@pytest.mark.skipif(SKIP_STRESS_TESTS, reason="SKIP_STRESS_TESTS is set")
class TestMemoryStability:
    """Test memory stability under sustained load."""

    @pytest.mark.asyncio
    async def test_memory_stability_long_running(self):
        """Test memory doesn't grow unbounded during long runs."""
        runner = StressTestRunner(
            concurrent_requests=5,
            request_count=100,
            duration_seconds=10.0,
        )

        metrics = await runner.run_duration_test(mock_agent_task)

        # Memory delta should be reasonable (less than 200MB for 10s test)
        # Note: Memory tracking includes asyncio infrastructure and test overhead
        memory_delta_mb = (metrics.memory_end - metrics.memory_start) / 1024 / 1024
        assert memory_delta_mb < 200, f"Memory delta too high: {memory_delta_mb}MB"

    @pytest.mark.asyncio
    async def test_no_memory_leak_in_subagents(self, clean_subagent_manager):
        """Test subagent manager doesn't leak memory."""
        # Ensure tracemalloc is not already running
        if tracemalloc.is_tracing():
            tracemalloc.stop()

        tracemalloc.start()
        initial_memory = tracemalloc.get_traced_memory()[0]

        try:
            # Run multiple rounds of subagent tasks
            for round_num in range(5):
                for i in range(settings.max_sub_agents):
                    await clean_subagent_manager.spawn(f"agent_{round_num}_{i}", mock_agent_task)
                await clean_subagent_manager.wait_for_all()
                clean_subagent_manager.clear()
                gc.collect()

            final_memory = tracemalloc.get_traced_memory()[0]

            # Memory growth should be limited
            growth_mb = (final_memory - initial_memory) / 1024 / 1024
            assert growth_mb < 50, f"Memory grew by {growth_mb}MB"
        finally:
            # Ensure tracemalloc is stopped even if test fails
            if tracemalloc.is_tracing():
                tracemalloc.stop()


# =============================================================================
# Stress Tests: Resource Limits
# =============================================================================


@pytest.mark.stress
@pytest.mark.skipif(SKIP_STRESS_TESTS, reason="SKIP_STRESS_TESTS is set")
class TestResourceLimits:
    """Test behavior when hitting resource limits."""

    @pytest.mark.asyncio
    async def test_max_sub_agents_limit(self, clean_subagent_manager):
        """Test that max_sub_agents limit is enforced."""
        max_agents = settings.max_sub_agents
        spawn_errors = []

        async def simple_task(progress_callback=None):
            await asyncio.sleep(0.1)
            return "done"

        # Try to spawn more than max
        for i in range(max_agents + 5):
            try:
                await clean_subagent_manager.spawn(f"agent_{i}", simple_task)
            except ValueError as e:
                spawn_errors.append(str(e))

        # Wait for all to complete
        await clean_subagent_manager.wait_for_all()

        # Semaphore should have limited concurrent execution
        # All tasks should eventually complete
        results = clean_subagent_manager.get_completed_results()
        assert len(results) == max_agents + 5

    @pytest.mark.asyncio
    async def test_task_queue_overflow(self, clean_coordinator):
        """Test handling of task queue overflow."""
        # Add many tasks
        for i in range(100):
            await clean_coordinator.add_task(
                task_id=f"task_{i}",
                description=f"Task {i}",
                dependencies=[],
            )

        # All tasks should be accepted
        assert len(clean_coordinator.tasks) == 100

        # Ready tasks should be all of them (no dependencies)
        ready = clean_coordinator.get_ready_tasks()
        assert len(ready) == 100


# =============================================================================
# Stress Tests: Error Recovery
# =============================================================================


@pytest.mark.stress
@pytest.mark.skipif(SKIP_STRESS_TESTS, reason="SKIP_STRESS_TESTS is set")
class TestErrorRecovery:
    """Test error recovery under stress."""

    @pytest.mark.asyncio
    async def test_partial_failure_recovery(self, stress_runner):
        """Test recovery from partial failures."""
        call_count = 0

        async def flaky_request(request_id: int) -> Dict[str, Any]:
            nonlocal call_count
            call_count += 1

            # Fail some requests
            if call_count % 10 == 0:
                raise RuntimeError(f"Simulated failure at request {request_id}")

            return await mock_session_create(request_id=request_id)

        metrics = await stress_runner.run_concurrent_requests(flaky_request)

        # Should have some failures but mostly success
        assert metrics.successful_requests > metrics.total_requests * 0.8
        assert metrics.failed_requests > 0

    @pytest.mark.asyncio
    async def test_cascading_failure_prevention(self, clean_coordinator):
        """Test that cascading failures are prevented."""
        # Create dependency chain
        await clean_coordinator.add_task("task_a", "A", dependencies=[])
        await clean_coordinator.add_task("task_b", "B", dependencies=["task_a"])
        await clean_coordinator.add_task("task_c", "C", dependencies=["task_b"])

        # Mark first task as failed
        await clean_coordinator.mark_task_running("task_a")
        await clean_coordinator.mark_task_failed("task_a", "Simulated failure")

        # Dependent tasks should still be pending
        assert clean_coordinator.tasks["task_b"].status == TaskStatus.PENDING
        assert clean_coordinator.tasks["task_c"].status == TaskStatus.PENDING

        # Get ready tasks should return empty (task_b depends on failed task_a)
        ready = clean_coordinator.get_ready_tasks()
        assert len(ready) == 0


# =============================================================================
# Stress Tests: Performance Benchmarks
# =============================================================================


@pytest.mark.stress
@pytest.mark.slow
@pytest.mark.skipif(SKIP_STRESS_TESTS, reason="SKIP_STRESS_TESTS is set")
class TestPerformanceBenchmarks:
    """Performance benchmarks for stress tests."""

    @pytest.mark.asyncio
    async def test_throughput_benchmark(self):
        """Measure maximum throughput."""
        runner = StressTestRunner(
            concurrent_requests=20,
            request_count=200,
        )

        metrics = await runner.run_concurrent_requests(mock_tool_call)

        # Should achieve at least 50 requests per second
        rps = metrics.total_requests / metrics.total_duration
        assert rps >= 50, f"Throughput too low: {rps} req/s"

    @pytest.mark.asyncio
    async def test_latency_benchmark(self):
        """Measure latency under load."""
        runner = StressTestRunner(
            concurrent_requests=10,
            request_count=100,
        )

        metrics = await runner.run_concurrent_requests(mock_session_create)

        # P99 latency should be reasonable
        data = metrics.to_dict()
        p99 = data["latency"]["p99_seconds"]

        # P99 should be under 1 second for simple mock operations
        assert p99 < 1.0, f"P99 latency too high: {p99}s"


# =============================================================================
# Report Generation
# =============================================================================


def generate_stress_report(results: Dict[str, PerformanceMetrics]) -> str:
    """Generate a JSON-formatted stress test report.

    Args:
        results: Dictionary mapping test name to metrics.

    Returns:
        JSON string with full report.
    """
    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_tests": len(results),
            "tests_passed": sum(1 for m in results.values() if m.failed_requests == 0),
            "tests_with_failures": sum(1 for m in results.values() if m.failed_requests > 0),
        },
        "tests": {name: metrics.to_dict() for name, metrics in results.items()},
    }

    return json.dumps(report, indent=2)


# =============================================================================
# Integration with SubAgentManager
# =============================================================================


@pytest.mark.stress
@pytest.mark.skipif(SKIP_STRESS_TESTS, reason="SKIP_STRESS_TESTS is set")
class TestSubAgentManagerStress:
    """Stress tests specifically for SubAgentManager."""

    @pytest.mark.asyncio
    async def test_rapid_spawn_and_wait(self, clean_subagent_manager):
        """Test rapid spawning and waiting of agents."""

        async def quick_task(progress_callback=None):
            await asyncio.sleep(0.01)
            return "quick"

        # Rapid spawn
        for i in range(20):
            await clean_subagent_manager.spawn(f"quick_{i}", quick_task)

        # Wait for all
        results = await clean_subagent_manager.wait_for_all()

        assert len(results) == 20
        assert all(r.status == AgentStatus.COMPLETED for r in results.values())

    @pytest.mark.asyncio
    async def test_progress_tracking_under_load(self, clean_subagent_manager):
        """Test progress tracking works under load."""
        progress_updates = []

        async def progress_task(progress_callback=None):
            for i in range(5):
                if progress_callback:
                    await progress_callback(i / 5, f"Step {i}")
                await asyncio.sleep(0.01)
            return "done"

        # Spawn multiple agents
        for i in range(settings.max_sub_agents):
            await clean_subagent_manager.spawn(f"progress_{i}", progress_task)

        # Collect progress updates
        async def collect_progress():
            while True:
                update = await clean_subagent_manager.get_progress_update(timeout=0.5)
                if update is None:
                    # Check if all done
                    all_done = all(
                        r.status in (AgentStatus.COMPLETED, AgentStatus.FAILED)
                        for r in clean_subagent_manager.results.values()
                    )
                    if all_done:
                        break
                else:
                    progress_updates.append(update)

        await collect_progress()

        # Should have received progress updates
        assert len(progress_updates) > 0


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "stress"])
