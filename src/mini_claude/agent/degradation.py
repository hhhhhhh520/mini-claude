"""Degradation strategies for production-grade Agent reliability.

This module implements multiple degradation strategies:
1. ModelDegradation: Fallback to backup models when primary fails
2. ExponentialBackoff: Retry with exponential backoff and jitter
3. ToolDegradation: Skip or replace failing tools
4. StrategyDegradation: Degrade from Reflexion to ReAct for complex tasks
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime

from mini_claude.utils.logger import get_logger

logger = get_logger(__name__)


class DegradationType(str, Enum):
    """Types of degradation events."""

    MODEL = "model"
    TOOL = "tool"
    STRATEGY = "strategy"
    CONTEXT = "context"


@dataclass
class DegradationEvent:
    """Record of a degradation event."""

    type: DegradationType
    timestamp: datetime
    from_value: str
    to_value: str
    reason: str
    success: Optional[bool] = None


@dataclass
class DegradationHistory:
    """History of all degradation events."""

    events: List[DegradationEvent] = field(default_factory=list)
    max_events: int = 100

    def add(self, event: DegradationEvent) -> None:
        """Add an event to history."""
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events :]

    def get_recent(self, count: int = 10) -> List[DegradationEvent]:
        """Get recent events."""
        return self.events[-count:]

    def get_by_type(self, dtype: DegradationType) -> List[DegradationEvent]:
        """Get events by type."""
        return [e for e in self.events if e.type == dtype]


class ModelDegradation:
    """Model fallback strategy with automatic failover.

    When the primary model fails, automatically switch to backup models.
    Supports manual reset and tracks degradation history.

    Example:
        config = {
            "primary": "deepseek-chat",
            "fallbacks": ["gpt-4o-mini", "claude-3-haiku-20240307"],
        }
        degr = ModelDegradation(config)
        model = degr.get_current_model()  # "deepseek-chat"
        degr.record_failure("deepseek-chat", "API timeout")
        model = degr.get_current_model()  # "gpt-4o-mini"
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize model degradation.

        Args:
            config: Configuration dict with keys:
                - primary: Primary model name
                - fallbacks: List of fallback model names
                - max_failures: Max failures before switching (default: 2)
                - reset_after_seconds: Auto-reset to primary after N seconds (default: 300)
        """
        config = config or {}
        self.primary = config.get("primary", "deepseek-chat")
        self.fallbacks = config.get("fallbacks", [])
        self.max_failures = config.get("max_failures", 2)
        self.reset_after_seconds = config.get("reset_after_seconds", 300)

        self._current_index = 0
        self._failure_counts: Dict[str, int] = {}
        self._last_failure_time: Optional[float] = None
        self.history = DegradationHistory()

        # Build model chain: primary + fallbacks
        self._model_chain = [self.primary] + self.fallbacks

    def get_current_model(self) -> str:
        """Get the current active model."""
        # Auto-reset to primary if enough time has passed
        if self._should_auto_reset():
            self._reset_to_primary()

        return self._model_chain[self._current_index]

    def get_model_chain(self) -> List[str]:
        """Get the full model chain."""
        return self._model_chain.copy()

    def record_failure(self, model: str, reason: str) -> str:
        """Record a model failure and potentially switch to fallback.

        Args:
            model: The model that failed
            reason: Failure reason

        Returns:
            The new current model (may be same if not degraded)
        """
        self._failure_counts[model] = self._failure_counts.get(model, 0) + 1
        self._last_failure_time = time.time()

        logger.warning(
            "Model failure recorded",
            model=model,
            reason=reason,
            failure_count=self._failure_counts[model],
        )

        # Check if we should degrade
        if self._failure_counts[model] >= self.max_failures:
            if self._current_index < len(self._model_chain) - 1:
                old_model = self._model_chain[self._current_index]
                self._current_index += 1
                new_model = self._model_chain[self._current_index]

                event = DegradationEvent(
                    type=DegradationType.MODEL,
                    timestamp=datetime.now(),
                    from_value=old_model,
                    to_value=new_model,
                    reason=f"Failed {self._failure_counts[old_model]} times: {reason}",
                )
                self.history.add(event)

                logger.info(
                    "Model degraded",
                    from_model=old_model,
                    to_model=new_model,
                    reason=reason,
                )

                return new_model
            else:
                logger.error(
                    "No more fallback models available",
                    current_model=model,
                )

        return self.get_current_model()

    def record_success(self, model: str) -> None:
        """Record a successful model call."""
        self._failure_counts[model] = 0

    def reset(self) -> None:
        """Manually reset to primary model."""
        self._reset_to_primary()

    def _reset_to_primary(self) -> None:
        """Reset to primary model."""
        if self._current_index != 0:
            old_model = self._model_chain[self._current_index]
            self._current_index = 0
            self._failure_counts = {}

            event = DegradationEvent(
                type=DegradationType.MODEL,
                timestamp=datetime.now(),
                from_value=old_model,
                to_value=self.primary,
                reason="Manual or auto reset",
            )
            self.history.add(event)

            logger.info("Reset to primary model", model=self.primary)

    def _should_auto_reset(self) -> bool:
        """Check if we should auto-reset to primary."""
        if self._current_index == 0:
            return False
        if self._last_failure_time is None:
            return False
        return time.time() - self._last_failure_time > self.reset_after_seconds


class ExponentialBackoff:
    """Exponential backoff retry strategy with jitter.

    Implements retry with exponentially increasing delays and optional jitter
    to prevent thundering herd problems.

    Example:
        backoff = ExponentialBackoff(max_retries=3)
        for attempt in backoff:
            try:
                result = await call_api()
                break
            except Exception as e:
                await backoff.wait()
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize exponential backoff.

        Args:
            config: Configuration dict with keys:
                - max_retries: Maximum retry attempts (default: 3)
                - initial_delay: Initial delay in seconds (default: 1.0)
                - max_delay: Maximum delay in seconds (default: 30.0)
                - exponential_base: Base for exponential calculation (default: 2)
                - jitter: Add random jitter to delays (default: True)
        """
        config = config or {}
        self.max_retries = config.get("max_retries", 3)
        self.initial_delay = config.get("initial_delay", 1.0)
        self.max_delay = config.get("max_delay", 30.0)
        self.exponential_base = config.get("exponential_base", 2)
        self.jitter = config.get("jitter", True)

        self._current_attempt = 0
        self._total_retries = 0

    @property
    def current_attempt(self) -> int:
        """Get current attempt number (0-indexed)."""
        return self._current_attempt

    @property
    def total_retries(self) -> int:
        """Get total number of retries made."""
        return self._total_retries

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt.

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        delay = self.initial_delay * (self.exponential_base**attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            # Add random jitter: 0.5x to 1.5x
            delay = delay * (0.5 + random.random())

        return delay

    def should_retry(self) -> bool:
        """Check if we should retry."""
        return self._current_attempt <= self.max_retries

    async def wait(self) -> float:
        """Wait before next retry.

        Returns:
            Actual delay in seconds
        """
        if self._current_attempt > self.max_retries:
            raise RuntimeError(f"Max retries ({self.max_retries}) exceeded")

        delay = self.calculate_delay(self._current_attempt)
        self._current_attempt += 1
        self._total_retries += 1

        logger.debug(
            "Backoff wait",
            attempt=self._current_attempt,
            delay=delay,
        )

        await asyncio.sleep(delay)
        return delay

    def reset(self) -> None:
        """Reset attempt counter."""
        self._current_attempt = 0

    def __iter__(self):
        """Allow using in for loop."""
        self.reset()
        return self

    def __next__(self) -> int:
        """Get next attempt number or raise StopIteration."""
        if self.should_retry():
            attempt = self._current_attempt
            self._current_attempt += 1
            return attempt
        raise StopIteration


class ToolDegradation:
    """Tool failure tracking and degradation.

    Tracks tool failures and can skip or replace failing tools.
    Supports tool replacement mappings for graceful degradation.

    Example:
        degr = ToolDegradation()
        degr.record_failure("web_search", "API rate limit")
        if degr.should_skip("web_search"):
            # Skip this tool
            pass
        replacement = degr.get_replacement("web_search")  # "web_fetch"
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize tool degradation.

        Args:
            config: Configuration dict with keys:
                - max_failures: Max failures before skipping (default: 3)
                - reset_after_seconds: Reset failure count after N seconds (default: 600)
                - replacements: Dict mapping tool names to replacements
        """
        config = config or {}
        self.max_failures = config.get("max_failures", 3)
        self.reset_after_seconds = config.get("reset_after_seconds", 600)
        self.replacements = config.get(
            "replacements",
            {
                "web_search": "web_fetch",
                "run_command": "run_background",
            },
        )

        self._failure_counts: Dict[str, int] = {}
        self._last_failure_time: Dict[str, float] = {}
        self._disabled_tools: set = set()
        self.history = DegradationHistory()

    def record_failure(self, tool: str, reason: str) -> None:
        """Record a tool failure.

        Args:
            tool: Tool name that failed
            reason: Failure reason
        """
        self._failure_counts[tool] = self._failure_counts.get(tool, 0) + 1
        self._last_failure_time[tool] = time.time()

        logger.warning(
            "Tool failure recorded",
            tool=tool,
            reason=reason,
            failure_count=self._failure_counts[tool],
        )

        # Check if we should disable this tool
        if self._failure_counts[tool] >= self.max_failures:
            self._disabled_tools.add(tool)

            event = DegradationEvent(
                type=DegradationType.TOOL,
                timestamp=datetime.now(),
                from_value=tool,
                to_value="disabled",
                reason=f"Failed {self._failure_counts[tool]} times: {reason}",
            )
            self.history.add(event)

            logger.warning(
                "Tool disabled due to failures",
                tool=tool,
                failure_count=self._failure_counts[tool],
            )

    def record_success(self, tool: str) -> None:
        """Record a successful tool call."""
        self._failure_counts[tool] = 0
        self._disabled_tools.discard(tool)

    def should_skip(self, tool: str) -> bool:
        """Check if a tool should be skipped.

        Args:
            tool: Tool name

        Returns:
            True if tool should be skipped
        """
        # Check if auto-reset applies
        if tool in self._last_failure_time:
            if time.time() - self._last_failure_time[tool] > self.reset_after_seconds:
                self._failure_counts[tool] = 0
                self._disabled_tools.discard(tool)

        return tool in self._disabled_tools

    def get_replacement(self, tool: str) -> Optional[str]:
        """Get replacement tool if available.

        Args:
            tool: Original tool name

        Returns:
            Replacement tool name or None
        """
        return self.replacements.get(tool)

    def get_disabled_tools(self) -> List[str]:
        """Get list of disabled tools."""
        return list(self._disabled_tools)

    def get_failure_stats(self) -> Dict[str, int]:
        """Get failure statistics for all tools."""
        return self._failure_counts.copy()

    def reset(self, tool: Optional[str] = None) -> None:
        """Reset failure counts.

        Args:
            tool: Specific tool to reset, or None for all
        """
        if tool:
            self._failure_counts.pop(tool, None)
            self._last_failure_time.pop(tool, None)
            self._disabled_tools.discard(tool)
        else:
            self._failure_counts.clear()
            self._last_failure_time.clear()
            self._disabled_tools.clear()


class StrategyDegradation:
    """Strategy degradation from complex to simple approaches.

    When a complex strategy (e.g., Reflexion) fails, degrade to a
    simpler strategy (e.g., ReAct).

    Example:
        degr = StrategyDegradation()
        strategy = degr.get_current_strategy()  # "reflexion"
        degr.record_failure("reflexion", "Max iterations exceeded")
        strategy = degr.get_current_strategy()  # "react"
    """

    # Strategy complexity levels (higher = more complex)
    STRATEGY_LEVELS = {
        "reflexion": 3,
        "react": 2,
        "simple": 1,
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize strategy degradation.

        Args:
            config: Configuration dict with keys:
                - initial_strategy: Starting strategy (default: "react")
                - max_failures: Failures before degrading (default: 2)
        """
        config = config or {}
        self.initial_strategy = config.get("initial_strategy", "react")
        self.max_failures = config.get("max_failures", 2)

        self._current_strategy = self.initial_strategy
        self._failure_counts: Dict[str, int] = {}
        self.history = DegradationHistory()

    def get_current_strategy(self) -> str:
        """Get current strategy."""
        return self._current_strategy

    def record_failure(self, strategy: str, reason: str) -> str:
        """Record a strategy failure and potentially degrade.

        Args:
            strategy: Strategy that failed
            reason: Failure reason

        Returns:
            New current strategy
        """
        self._failure_counts[strategy] = self._failure_counts.get(strategy, 0) + 1

        logger.warning(
            "Strategy failure recorded",
            strategy=strategy,
            reason=reason,
            failure_count=self._failure_counts[strategy],
        )

        # Check if we should degrade
        if self._failure_counts[strategy] >= self.max_failures:
            new_strategy = self._get_simpler_strategy()
            if new_strategy and new_strategy != self._current_strategy:
                event = DegradationEvent(
                    type=DegradationType.STRATEGY,
                    timestamp=datetime.now(),
                    from_value=self._current_strategy,
                    to_value=new_strategy,
                    reason=f"Failed {self._failure_counts[strategy]} times: {reason}",
                )
                self.history.add(event)

                self._current_strategy = new_strategy

                logger.info(
                    "Strategy degraded",
                    from_strategy=strategy,
                    to_strategy=new_strategy,
                    reason=reason,
                )

        return self._current_strategy

    def record_success(self, strategy: str) -> None:
        """Record a successful strategy execution."""
        self._failure_counts[strategy] = 0

    def reset(self) -> None:
        """Reset to initial strategy."""
        self._current_strategy = self.initial_strategy
        self._failure_counts.clear()

    def _get_simpler_strategy(self) -> Optional[str]:
        """Get a simpler strategy than current."""
        current_level = self.STRATEGY_LEVELS.get(self._current_strategy, 0)

        for strategy, level in sorted(
            self.STRATEGY_LEVELS.items(), key=lambda x: x[1], reverse=True
        ):
            if level < current_level:
                return strategy

        return None


class DegradationManager:
    """Central manager for all degradation strategies.

    Provides a unified interface for model, tool, and strategy degradation.

    Example:
        manager = DegradationManager({
            "model": {"primary": "deepseek-chat", "fallbacks": ["gpt-4o-mini"]},
            "backoff": {"max_retries": 3},
            "tool": {"max_failures": 3},
            "strategy": {"initial_strategy": "react"},
        })

        # Execute with automatic degradation
        result = await manager.execute_with_degradation(
            llm_call,
            messages,
            tools,
        )
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize degradation manager.

        Args:
            config: Configuration dict with keys:
                - model: ModelDegradation config
                - backoff: ExponentialBackoff config
                - tool: ToolDegradation config
                - strategy: StrategyDegradation config
                - enabled: Enable/disable all degradation (default: True)
        """
        config = config or {}
        self.enabled = config.get("enabled", True)

        self.model = ModelDegradation(config.get("model", {}))
        self.backoff = ExponentialBackoff(config.get("backoff", {}))
        self.tool = ToolDegradation(config.get("tool", {}))
        self.strategy = StrategyDegradation(config.get("strategy", {}))

        self._combined_history = DegradationHistory()

    def get_history(self) -> List[DegradationEvent]:
        """Get combined degradation history."""
        events = []
        events.extend(self.model.history.events)
        events.extend(self.tool.history.events)
        events.extend(self.strategy.history.events)
        return sorted(events, key=lambda e: e.timestamp)

    def reset_all(self) -> None:
        """Reset all degradation strategies."""
        self.model.reset()
        self.backoff.reset()
        self.tool.reset()
        self.strategy.reset()

    def get_status(self) -> Dict[str, Any]:
        """Get current degradation status."""
        return {
            "enabled": self.enabled,
            "model": {
                "current": self.model.get_current_model(),
                "chain": self.model.get_model_chain(),
            },
            "backoff": {
                "current_attempt": self.backoff.current_attempt,
                "max_retries": self.backoff.max_retries,
            },
            "tool": {
                "disabled": self.tool.get_disabled_tools(),
                "failure_stats": self.tool.get_failure_stats(),
            },
            "strategy": {
                "current": self.strategy.get_current_strategy(),
            },
        }
