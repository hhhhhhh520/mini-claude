"""Tests for degradation strategies."""

import pytest
from datetime import datetime

from mini_claude.agent.degradation import (
    DegradationType,
    DegradationEvent,
    DegradationHistory,
    ModelDegradation,
    ExponentialBackoff,
    ToolDegradation,
    StrategyDegradation,
    DegradationManager,
)


# =============================================================================
# ModelDegradation Tests
# =============================================================================

class TestModelDegradation:
    """Tests for ModelDegradation class."""

    def test_initial_state(self):
        """Test initial state is correct."""
        degr = ModelDegradation({
            "primary": "deepseek-chat",
            "fallbacks": ["gpt-4o-mini", "claude-3-haiku"],
        })

        assert degr.get_current_model() == "deepseek-chat"
        assert degr.get_model_chain() == ["deepseek-chat", "gpt-4o-mini", "claude-3-haiku"]

    def test_no_fallbacks(self):
        """Test with no fallback models."""
        degr = ModelDegradation({"primary": "deepseek-chat"})

        assert degr.get_current_model() == "deepseek-chat"
        assert degr.get_model_chain() == ["deepseek-chat"]

    def test_record_failure_degrades(self):
        """Test that recording failures triggers degradation."""
        degr = ModelDegradation({
            "primary": "deepseek-chat",
            "fallbacks": ["gpt-4o-mini"],
            "max_failures": 2,
        })

        # First failure - no degradation yet
        model = degr.record_failure("deepseek-chat", "API timeout")
        assert model == "deepseek-chat"

        # Second failure - should degrade
        model = degr.record_failure("deepseek-chat", "API timeout")
        assert model == "gpt-4o-mini"

        # Check history
        events = degr.history.get_by_type(DegradationType.MODEL)
        assert len(events) == 1
        assert events[0].from_value == "deepseek-chat"
        assert events[0].to_value == "gpt-4o-mini"

    def test_no_more_fallbacks(self):
        """Test behavior when no more fallbacks available."""
        degr = ModelDegradation({
            "primary": "deepseek-chat",
            "fallbacks": ["gpt-4o-mini"],
            "max_failures": 1,
        })

        # Degrade to fallback
        degr.record_failure("deepseek-chat", "Error")
        assert degr.get_current_model() == "gpt-4o-mini"

        # Fallback also fails - should stay on fallback
        model = degr.record_failure("gpt-4o-mini", "Error")
        assert model == "gpt-4o-mini"

    def test_record_success(self):
        """Test that success resets failure count."""
        degr = ModelDegradation({
            "primary": "deepseek-chat",
            "fallbacks": ["gpt-4o-mini"],
            "max_failures": 2,
        })

        degr.record_failure("deepseek-chat", "Error")
        degr.record_success("deepseek-chat")

        # Failure count should be reset
        degr.record_failure("deepseek-chat", "Error")
        assert degr.get_current_model() == "deepseek-chat"

    def test_manual_reset(self):
        """Test manual reset to primary."""
        degr = ModelDegradation({
            "primary": "deepseek-chat",
            "fallbacks": ["gpt-4o-mini"],
            "max_failures": 1,
        })

        degr.record_failure("deepseek-chat", "Error")
        assert degr.get_current_model() == "gpt-4o-mini"

        degr.reset()
        assert degr.get_current_model() == "deepseek-chat"

    def test_auto_reset(self):
        """Test auto-reset after timeout."""
        degr = ModelDegradation({
            "primary": "deepseek-chat",
            "fallbacks": ["gpt-4o-mini"],
            "max_failures": 1,
            "reset_after_seconds": 0.1,  # 100ms for testing
        })

        degr.record_failure("deepseek-chat", "Error")
        assert degr.get_current_model() == "gpt-4o-mini"

        # Wait for auto-reset
        import time
        time.sleep(0.15)

        assert degr.get_current_model() == "deepseek-chat"


# =============================================================================
# ExponentialBackoff Tests
# =============================================================================

class TestExponentialBackoff:
    """Tests for ExponentialBackoff class."""

    def test_initial_state(self):
        """Test initial state."""
        backoff = ExponentialBackoff({"max_retries": 3})

        assert backoff.current_attempt == 0
        assert backoff.should_retry() is True

    def test_calculate_delay(self):
        """Test delay calculation."""
        backoff = ExponentialBackoff({
            "initial_delay": 1.0,
            "max_delay": 30.0,
            "exponential_base": 2,
            "jitter": False,
        })

        assert backoff.calculate_delay(0) == 1.0
        assert backoff.calculate_delay(1) == 2.0
        assert backoff.calculate_delay(2) == 4.0
        assert backoff.calculate_delay(10) == 30.0  # Capped at max_delay

    def test_calculate_delay_with_jitter(self):
        """Test delay calculation with jitter."""
        backoff = ExponentialBackoff({
            "initial_delay": 1.0,
            "jitter": True,
        })

        # With jitter, delay should be between 0.5x and 1.5x
        for _ in range(10):
            delay = backoff.calculate_delay(0)
            assert 0.5 <= delay <= 1.5

    @pytest.mark.asyncio
    async def test_wait(self):
        """Test async wait."""
        backoff = ExponentialBackoff({
            "max_retries": 2,
            "initial_delay": 0.01,  # Fast for testing
            "jitter": False,
        })

        delay = await backoff.wait()
        assert delay == 0.01
        assert backoff.current_attempt == 1

        delay = await backoff.wait()
        assert delay == 0.02
        assert backoff.current_attempt == 2

    @pytest.mark.asyncio
    async def test_wait_exceeds_max_retries(self):
        """Test that wait raises error after max retries."""
        backoff = ExponentialBackoff({
            "max_retries": 1,
            "initial_delay": 0.01,
        })

        # First wait (attempt 0)
        await backoff.wait()
        # Second wait (attempt 1)
        await backoff.wait()
        # Third wait should fail (attempt 2 > max_retries=1)
        with pytest.raises(RuntimeError, match="Max retries"):
            await backoff.wait()

    def test_reset(self):
        """Test reset."""
        backoff = ExponentialBackoff({"max_retries": 3})

        backoff._current_attempt = 2
        backoff.reset()

        assert backoff.current_attempt == 0

    def test_iterator(self):
        """Test using as iterator."""
        backoff = ExponentialBackoff({"max_retries": 2, "jitter": False})

        # Reset and iterate
        backoff.reset()
        attempts = list(backoff)
        # max_retries=2 means attempts 0, 1, 2 (3 total)
        assert len(attempts) == 3
        assert attempts == [0, 1, 2]


# =============================================================================
# ToolDegradation Tests
# =============================================================================

class TestToolDegradation:
    """Tests for ToolDegradation class."""

    def test_initial_state(self):
        """Test initial state."""
        degr = ToolDegradation()

        assert degr.should_skip("web_search") is False
        assert degr.get_disabled_tools() == []

    def test_record_failure(self):
        """Test recording tool failures."""
        degr = ToolDegradation({"max_failures": 2})

        degr.record_failure("web_search", "API error")
        assert degr.should_skip("web_search") is False

        degr.record_failure("web_search", "API error")
        assert degr.should_skip("web_search") is True
        assert "web_search" in degr.get_disabled_tools()

    def test_record_success(self):
        """Test recording tool success."""
        degr = ToolDegradation({"max_failures": 2})

        degr.record_failure("web_search", "Error")
        degr.record_failure("web_search", "Error")
        assert degr.should_skip("web_search") is True

        degr.record_success("web_search")
        assert degr.should_skip("web_search") is False

    def test_get_replacement(self):
        """Test tool replacement."""
        degr = ToolDegradation({
            "replacements": {
                "web_search": "web_fetch",
            }
        })

        assert degr.get_replacement("web_search") == "web_fetch"
        assert degr.get_replacement("unknown_tool") is None

    def test_failure_stats(self):
        """Test failure statistics."""
        degr = ToolDegradation()

        degr.record_failure("web_search", "Error 1")
        degr.record_failure("web_search", "Error 2")
        degr.record_failure("run_command", "Error 3")

        stats = degr.get_failure_stats()
        assert stats["web_search"] == 2
        assert stats["run_command"] == 1

    def test_reset_single_tool(self):
        """Test resetting single tool."""
        degr = ToolDegradation({"max_failures": 1})

        degr.record_failure("web_search", "Error")
        degr.record_failure("run_command", "Error")

        degr.reset("web_search")

        assert degr.should_skip("web_search") is False
        assert degr.should_skip("run_command") is True

    def test_reset_all(self):
        """Test resetting all tools."""
        degr = ToolDegradation({"max_failures": 1})

        degr.record_failure("web_search", "Error")
        degr.record_failure("run_command", "Error")

        degr.reset()

        assert degr.get_disabled_tools() == []

    def test_auto_reset(self):
        """Test auto-reset after timeout."""
        degr = ToolDegradation({
            "max_failures": 1,
            "reset_after_seconds": 0.1,
        })

        degr.record_failure("web_search", "Error")
        assert degr.should_skip("web_search") is True

        import time
        time.sleep(0.15)

        assert degr.should_skip("web_search") is False


# =============================================================================
# StrategyDegradation Tests
# =============================================================================

class TestStrategyDegradation:
    """Tests for StrategyDegradation class."""

    def test_initial_state(self):
        """Test initial state."""
        degr = StrategyDegradation({"initial_strategy": "react"})

        assert degr.get_current_strategy() == "react"

    def test_record_failure_degrades(self):
        """Test that failures trigger strategy degradation."""
        degr = StrategyDegradation({
            "initial_strategy": "reflexion",
            "max_failures": 1,
        })

        assert degr.get_current_strategy() == "reflexion"

        degr.record_failure("reflexion", "Max iterations exceeded")
        assert degr.get_current_strategy() == "react"

    def test_degrade_to_simple(self):
        """Test degradation chain: reflexion -> react -> simple."""
        degr = StrategyDegradation({
            "initial_strategy": "reflexion",
            "max_failures": 1,
        })

        degr.record_failure("reflexion", "Error")
        assert degr.get_current_strategy() == "react"

        degr.record_failure("react", "Error")
        assert degr.get_current_strategy() == "simple"

        # No simpler strategy
        degr.record_failure("simple", "Error")
        assert degr.get_current_strategy() == "simple"

    def test_record_success(self):
        """Test success resets failure count."""
        degr = StrategyDegradation({
            "initial_strategy": "reflexion",
            "max_failures": 2,
        })

        degr.record_failure("reflexion", "Error")
        degr.record_success("reflexion")
        degr.record_failure("reflexion", "Error")

        assert degr.get_current_strategy() == "reflexion"

    def test_reset(self):
        """Test manual reset."""
        degr = StrategyDegradation({
            "initial_strategy": "reflexion",
            "max_failures": 1,
        })

        degr.record_failure("reflexion", "Error")
        assert degr.get_current_strategy() == "react"

        degr.reset()
        assert degr.get_current_strategy() == "reflexion"


# =============================================================================
# DegradationManager Tests
# =============================================================================

class TestDegradationManager:
    """Tests for DegradationManager class."""

    def test_initial_state(self):
        """Test initial state."""
        manager = DegradationManager({
            "model": {"primary": "deepseek-chat"},
            "backoff": {"max_retries": 3},
            "tool": {"max_failures": 3},
            "strategy": {"initial_strategy": "react"},
        })

        status = manager.get_status()

        assert status["enabled"] is True
        assert status["model"]["current"] == "deepseek-chat"
        assert status["backoff"]["max_retries"] == 3
        assert status["strategy"]["current"] == "react"

    def test_disabled(self):
        """Test disabled manager."""
        manager = DegradationManager({"enabled": False})

        assert manager.enabled is False

    def test_reset_all(self):
        """Test resetting all strategies."""
        manager = DegradationManager({
            "model": {"primary": "deepseek-chat", "fallbacks": ["gpt-4o-mini"], "max_failures": 1},
            "strategy": {"initial_strategy": "reflexion", "max_failures": 1},
        })

        # Degrade model and strategy
        manager.model.record_failure("deepseek-chat", "Error")
        manager.strategy.record_failure("reflexion", "Error")

        assert manager.model.get_current_model() == "gpt-4o-mini"
        assert manager.strategy.get_current_strategy() == "react"

        manager.reset_all()

        assert manager.model.get_current_model() == "deepseek-chat"
        assert manager.strategy.get_current_strategy() == "reflexion"

    def test_get_history(self):
        """Test getting combined history."""
        manager = DegradationManager({
            "model": {"primary": "deepseek-chat", "fallbacks": ["gpt-4o-mini"], "max_failures": 1},
            "tool": {"max_failures": 1},
        })

        # Create some events
        manager.model.record_failure("deepseek-chat", "Error")
        manager.tool.record_failure("web_search", "Error")
        manager.tool.record_failure("web_search", "Error")

        history = manager.get_history()

        # Should have 2 events: model degradation + tool degradation
        assert len(history) >= 2
        types = [e.type for e in history]
        assert DegradationType.MODEL in types
        assert DegradationType.TOOL in types


# =============================================================================
# DegradationHistory Tests
# =============================================================================

class TestDegradationHistory:
    """Tests for DegradationHistory class."""

    def test_add_event(self):
        """Test adding events."""
        history = DegradationHistory(max_events=5)

        for i in range(10):
            history.add(DegradationEvent(
                type=DegradationType.MODEL,
                timestamp=datetime.now(),
                from_value=f"model_{i}",
                to_value=f"model_{i+1}",
                reason="test",
            ))

        assert len(history.events) == 5  # Max 5 events
        assert history.events[0].from_value == "model_5"  # Oldest kept

    def test_get_recent(self):
        """Test getting recent events."""
        history = DegradationHistory()

        for i in range(5):
            history.add(DegradationEvent(
                type=DegradationType.MODEL,
                timestamp=datetime.now(),
                from_value=f"model_{i}",
                to_value=f"model_{i+1}",
                reason="test",
            ))

        recent = history.get_recent(3)
        assert len(recent) == 3
        assert recent[0].from_value == "model_2"

    def test_get_by_type(self):
        """Test filtering by type."""
        history = DegradationHistory()

        history.add(DegradationEvent(
            type=DegradationType.MODEL,
            timestamp=datetime.now(),
            from_value="a",
            to_value="b",
            reason="test",
        ))
        history.add(DegradationEvent(
            type=DegradationType.TOOL,
            timestamp=datetime.now(),
            from_value="c",
            to_value="d",
            reason="test",
        ))
        history.add(DegradationEvent(
            type=DegradationType.MODEL,
            timestamp=datetime.now(),
            from_value="e",
            to_value="f",
            reason="test",
        ))

        model_events = history.get_by_type(DegradationType.MODEL)
        assert len(model_events) == 2

        tool_events = history.get_by_type(DegradationType.TOOL)
        assert len(tool_events) == 1


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for degradation strategies."""

    @pytest.mark.asyncio
    async def test_full_degradation_flow(self):
        """Test complete degradation flow."""
        manager = DegradationManager({
            "model": {
                "primary": "deepseek-chat",
                "fallbacks": ["gpt-4o-mini"],
                "max_failures": 1,
            },
            "backoff": {
                "max_retries": 1,
                "initial_delay": 0.01,
            },
            "tool": {
                "max_failures": 1,
            },
        })

        # Simulate model failure
        manager.model.record_failure("deepseek-chat", "API timeout")
        assert manager.model.get_current_model() == "gpt-4o-mini"

        # Simulate tool failure
        manager.tool.record_failure("web_search", "Rate limit")
        manager.tool.record_failure("web_search", "Rate limit")
        assert manager.tool.should_skip("web_search") is True

        # Check status
        status = manager.get_status()
        assert status["model"]["current"] == "gpt-4o-mini"
        assert "web_search" in status["tool"]["disabled"]

        # Reset all
        manager.reset_all()
        status = manager.get_status()
        assert status["model"]["current"] == "deepseek-chat"
        assert status["tool"]["disabled"] == []
